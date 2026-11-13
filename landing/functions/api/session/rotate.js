import { handleRotate } from "../../_auth.js";

export function onRequestPost(context) {
  return handleRotate(context);
}
