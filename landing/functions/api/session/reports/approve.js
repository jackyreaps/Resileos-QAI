import { handleReportsApprove } from "../../../_reports.js";

export function onRequestPost(context) {
  return handleReportsApprove(context);
}
