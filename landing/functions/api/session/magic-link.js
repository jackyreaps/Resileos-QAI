import { handleMagicLink } from "../../_auth.js";

export function onRequestPost(context) {
  return handleMagicLink(context);
}
