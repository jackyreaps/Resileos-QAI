/* Hook for the persona individual tier.
 * The key, when passed, is only a request header. It is not stored. */
(function (global) {
  function query(opts) {
    var params = new URLSearchParams();
    if (opts.accountId) params.set("account_id", opts.accountId);
    if (opts.sessionId) params.set("session_id", opts.sessionId);
    return params.toString();
  }

  function call(method, path, opts, body) {
    var headers = { "Content-Type": "application/json" };
    if (opts.apiKey) headers["X-API-Key"] = opts.apiKey;
    if (opts.accountId) headers["X-Resileos-Account"] = opts.accountId;
    var suffix = query(opts);
    return fetch(path + (suffix ? "?" + suffix : ""), {
      method: method,
      headers: headers,
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("persona " + response.status);
      }
      return response.json();
    });
  }

  global.ResileosPersona = {
    list: function (opts) {
      return call("GET", "/api/v1/persona/individual", opts || {});
    },
    put: function (opts, fact) {
      return call(
        "PUT",
        "/api/v1/persona/individual/" + encodeURIComponent(fact.id),
        opts || {},
        fact
      );
    },
    remove: function (opts, factId) {
      return call(
        "DELETE",
        "/api/v1/persona/individual/" + encodeURIComponent(factId),
        opts || {}
      );
    },
    recall: function (opts) {
      return call("GET", "/api/v1/persona/recall", opts || {});
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
