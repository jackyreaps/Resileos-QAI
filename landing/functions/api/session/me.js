import { handleMe } from "../../_auth.js";

export function onRequestGet(context) {
  return handleMe(context);
}
