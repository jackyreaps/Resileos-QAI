import { handleReveal } from "../../_auth.js";

export function onRequestPost(context) {
  return handleReveal(context);
}
