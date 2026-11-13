import { handleLogin } from "../../_auth.js";

export function onRequestPost(context) {
  return handleLogin(context);
}
