/* Resileos stream parts: the typed message-part schema shared by chat,
 * Studio, and Admin, plus a small SSE reader with resume, cancel, and a
 * plain-request fallback. Our own code; no outside SDK.
 * Mirrors resileos.chat.stream.PART_SCHEMA (a test checks they match). */
(function () {
  "use strict";
  var SCHEMA = {
    start: ["stream_id", "run_id"],
    step: ["step", "status", "label", "detail"],
    token: ["content", "verified"],
    harness: ["confidence", "risk", "verified", "route", "budget"],
    cycle: ["stage", "label"],
    checkpoint: ["id", "verified"],
    evidence: ["sources", "attachments", "packet_hash"],
    eat: ["accepted", "abstained", "rejected"],
    address: ["name", "path", "code", "dominant"],
    abstain: ["status", "label"],
    separated: ["proposal", "reviewers", "applied", "blind"],
    final: ["answer", "apollo", "verified", "status", "assist"],
    error: ["label"],
    cancelled: ["label"],
    done: [],
  };

  function valid(part) {
    return !!part && typeof part === "object" && part.v === 1 && Object.prototype.hasOwnProperty.call(SCHEMA, part.type);
  }

  /* Split an SSE text buffer into complete events; returns [events, rest]. */
  // Case-insensitive merge: a caller's "Content-Type" must replace ours, not
  // be joined into "application/json, application/json" (servers reject that).
  function streamHeaders(extra) {
    var h = new Headers({ "content-type": "application/json", accept: "text/event-stream" });
    Object.keys(extra || {}).forEach(function (k) { h.set(k, extra[k]); });
    return h;
  }

  function parseSSE(buffer) {
    var events = [];
    var blocks = buffer.split("\n\n");
    var rest = blocks.pop();
    blocks.forEach(function (block) {
      var data = [];
      block.split("\n").forEach(function (line) { if (line.indexOf("data: ") === 0) data.push(line.slice(6)); });
      if (!data.length) return;
      try {
        var part = JSON.parse(data.join("\n"));
        if (valid(part)) events.push(part);
      } catch (err) { /* skip a bad block */ }
    });
    return [events, rest];
  }

  /* Plain-words chip for a part, or null. No jargon on the public page. */
  function chip(part) {
    if (part.type === "harness") return part.verified ? { kind: "accepted", text: "Checked" } : { kind: "unverified", text: "Not verified" };
    if (part.type === "cycle" && part.stage === "hermes") return { kind: "info", text: "Searched" };
    if (part.type === "abstain") return { kind: "abstain", text: part.label || "Doesn't know" };
    if (part.type === "cancelled") return { kind: "info", text: "Stopped" };
    if (part.type === "error") return { kind: "conflict", text: part.label || "Couldn't finish" };
    return null;
  }

  /* Stream one turn. opts: {url, body, headers, onPart, signal, resumeUrl(id), fallback()} */
  async function run(opts) {
    var lastSeq = 0;
    var streamId = null;
    var finished = false;
    function handle(parts) {
      parts.forEach(function (p) {
        if (p.seq) lastSeq = Math.max(lastSeq, p.seq);
        if (p.type === "start") streamId = p.stream_id;
        if (p.type === "done") finished = true;
        opts.onPart(p);
      });
    }
    async function pump(res) {
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buf = "";
      for (;;) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += decoder.decode(chunk.value, { stream: true });
        var out = parseSSE(buf);
        buf = out[1];
        handle(out[0]);
      }
      if (buf.trim()) handle(parseSSE(buf + "\n\n")[0]);
    }
    var res;
    try {
      res = await fetch(opts.url, { method: "POST", credentials: "same-origin", headers: streamHeaders(opts.headers), body: JSON.stringify(opts.body), signal: opts.signal });
    } catch (err) {
      if (opts.signal && opts.signal.aborted) return { cancelled: true, streamId: streamId };
      return opts.fallback ? { fallback: true, result: await opts.fallback() } : { error: true };
    }
    var type = res.headers.get("content-type") || "";
    if (!res.ok || !res.body || type.indexOf("text/event-stream") === -1) {
      if (res.status >= 400 && res.status < 500 && res.status !== 404) return { error: true, status: res.status, response: res };
      return opts.fallback ? { fallback: true, result: await opts.fallback() } : { error: true, status: res.status };
    }
    streamId = res.headers.get("x-stream-id") || streamId;
    for (var attempt = 0; attempt < 3; attempt++) {
      try {
        await pump(res);
      } catch (err) {
        if (opts.signal && opts.signal.aborted) return { cancelled: true, streamId: streamId };
      }
      if (finished || !streamId || !opts.resumeUrl) break;
      try {  // dropped mid-reply: resume after the last part we have
        res = await fetch(opts.resumeUrl(streamId) + "?after=" + lastSeq, { credentials: "same-origin", headers: { accept: "text/event-stream" }, signal: opts.signal });
        if (!res.ok || !res.body) break;
      } catch (err) { break; }
    }
    return { finished: finished, streamId: streamId, lastSeq: lastSeq };
  }

  window.ResileosParts = { SCHEMA: SCHEMA, valid: valid, parseSSE: parseSSE, chip: chip, run: run };
})();
