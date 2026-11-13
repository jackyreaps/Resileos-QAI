import { handleReportsReject } from "../../../_reports.js";

export function onRequestPost(context) {
  return handleReportsReject(context);
}
