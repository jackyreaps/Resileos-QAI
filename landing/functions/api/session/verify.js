import { handleVerify } from "../../_auth.js";

export function onRequestGet(context) {
  return handleVerify(context);
}
