import { handleAdminPage } from "../_admin.js";

export function onRequest(context) {
  return handleAdminPage({ request: context.request, env: context.env, next: context.next });
}
