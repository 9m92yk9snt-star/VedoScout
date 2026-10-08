import React from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";
import api from "../lib/api";
import ProfileAnalysisStatus from "./ProfileAnalysisStatus";
expect.extend(matchers);
jest.mock("../lib/api", () => ({ __esModule: true, ASSET_BASE: "", default: { get: jest.fn() } }));
jest.mock("react-router-dom", () => ({ Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a> }), { virtual: true });
const report = { id: "owned", status: "ready", is_paid: true, player_details: { player_name: "Orman02" }, full_report_status: "generating" };
const flush = async () => { await act(async () => {}); };
beforeEach(() => { jest.useFakeTimers(); jest.clearAllMocks(); });
afterEach(() => { cleanup(); jest.useRealTimers(); });
test("partial body remains pending; saved full body and ready unlock report", async () => {
  api.get.mockResolvedValueOnce({ data: { ...report, has_full_report: true, full_report_status: "finalizing" } }).mockResolvedValue({ data: { ...report, has_full_report: true, full_report_status: "ready" } });
  render(<ProfileAnalysisStatus reports={[report]} />); await flush();
  expect(screen.queryByRole("link", { name: "Open report" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "View analysis status" })).toHaveAttribute("href", "/report/owned");
  await act(async () => { jest.advanceTimersByTime(6000); });
  expect(screen.getByRole("link", { name: "Open report" })).toBeInTheDocument();
  await act(async () => { jest.advanceTimersByTime(18000); });
  expect(api.get).toHaveBeenCalledTimes(2);
});
test.each([[401, "Sign in again"], [403, "do not have access"], [404, "Report not found"]])("terminal access %i stops polling", async (code, message) => {
  api.get.mockRejectedValue({ response: { status: code } });
  render(<ProfileAnalysisStatus reports={[report]} />); await flush();
  expect(screen.getByText(new RegExp(message))).toBeInTheDocument();
  await act(async () => { jest.advanceTimersByTime(18000); });
  expect(api.get).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("link", { name: "Open report" })).not.toBeInTheDocument();
});
test("network failure reconnects without claiming ready; unmount cancels polling", async () => {
  api.get.mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ data: report });
  const view = render(<ProfileAnalysisStatus reports={[report]} />); await flush();
  expect(screen.getByText("Reconnecting to update status")).toBeInTheDocument();
  await act(async () => { jest.advanceTimersByTime(6000); });
  expect(api.get).toHaveBeenCalledTimes(2);
  view.unmount();
  await act(async () => { jest.advanceTimersByTime(18000); });
  expect(api.get).toHaveBeenCalledTimes(2);
});
test("ready without stored body remains observed", async () => {
  api.get.mockResolvedValue({ data: { ...report, full_report_status: "ready", has_full_report: false } });
  render(<ProfileAnalysisStatus reports={[report]} />); await flush();
  expect(screen.queryByRole("link", { name: "Open report" })).not.toBeInTheDocument();
  expect(screen.getByText("Running in background")).toBeInTheDocument();
});
