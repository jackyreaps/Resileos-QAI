import { handlePassword } from "../../_auth.js";

export function onRequestPost(context) {
  return handlePassword(context);
}
