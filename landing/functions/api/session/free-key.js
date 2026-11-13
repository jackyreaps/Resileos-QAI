import { handleFreeKey } from "../../_auth.js";

export function onRequestPost(context) {
  return handleFreeKey(context);
}
