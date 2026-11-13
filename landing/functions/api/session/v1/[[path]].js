import { handleProxy } from "../../../_auth.js";

export function onRequest(context) {
  return handleProxy(context);
}
