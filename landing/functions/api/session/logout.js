import { handleLogout } from "../../_auth.js";

export function onRequestPost(context) {
  return handleLogout(context);
}
