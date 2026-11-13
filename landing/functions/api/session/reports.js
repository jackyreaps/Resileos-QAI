import { handleReportsList } from "../../_reports.js";

export function onRequestGet(context) {
  return handleReportsList(context);
}
