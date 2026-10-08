import React from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";
import { toast } from "sonner";
import api from "../lib/api";
import BackgroundAnalysisTracker from "./BackgroundAnalysisTracker";
expect.extend(matchers);
jest.mock("../lib/api", () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
let mockRoute = "/reports";
const mockNavigate = jest.fn();
// CRA's Jest predates Router 7's exports map. Only navigation hooks are
// needed in this unit; the browser regression exercises the actual router.
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate, useLocation: () => ({ pathname: mockRoute }) }), { virtual: true });
const KEY = "scoutmeplay.activeAnalysis";
const paidPreview = { id: "selected", status: "ready", is_paid: true, preview: { brief_summary: "Initial" } };
beforeEach(() => {
  jest.useFakeTimers(); jest.clearAllMocks();
  localStorage.setItem(KEY, JSON.stringify({ id: "selected", startedAt: Date.now() - 45 * 60_000, playerName: "Orman02" }));
});
afterEach(() => { cleanup(); localStorage.clear(); jest.useRealTimers(); });
const mount = (route = "/reports") => { mockRoute = route; return render(<BackgroundAnalysisTracker />); };
const flush = async () => { await act(async () => {}); };

test("paid preview and finalization remain active; only saved ready full report notifies", async () => {
  api.get.mockResolvedValueOnce({ data: paidPreview })
    .mockResolvedValueOnce({ data: { ...paidPreview, has_full_report: true, full_report_status: "finalizing" } })
    .mockResolvedValue({ data: { ...paidPreview, has_full_report: true, full_report_status: "ready" } });
  mount(); await flush();
  expect(toast.success).not.toHaveBeenCalled();
  expect(screen.getByTestId("bg-analysis-tracker")).toHaveTextContent("Preparing the full analysis");
  await act(async () => { jest.advanceTimersByTime(5000); });
  expect(toast.success).not.toHaveBeenCalled();
  expect(screen.getByTestId("bg-analysis-tracker")).toHaveTextContent("Preparing your report");
  await act(async () => { jest.advanceTimersByTime(5000); });
  expect(toast.success).toHaveBeenCalledWith("Your full scout report is ready!", expect.any(Object));
  expect(localStorage.getItem(KEY)).toBeNull();
});

test("free report notification explicitly says initial preview", async () => {
  api.get.mockResolvedValue({ data: { ...paidPreview, is_paid: false } });
  mount(); await flush();
  expect(toast.success).toHaveBeenCalledWith("Your initial preview is ready", expect.any(Object));
});

test("explicit ready without a body remains incomplete", async () => {
  api.get.mockResolvedValue({ data: { ...paidPreview, full_report_status: "ready", has_full_report: false } });
  mount(); await flush();
  expect(toast.success).not.toHaveBeenCalled();
  expect(screen.getByTestId("bg-analysis-tracker")).toBeInTheDocument();
});

test("the report route owns its status stream and suppresses the duplicate pill", async () => {
  api.get.mockResolvedValue({ data: paidPreview });
  mount("/report/selected"); await flush();
  expect(api.get).not.toHaveBeenCalled();
  expect(screen.queryByTestId("bg-analysis-tracker")).not.toBeInTheDocument();
});

test("a full-report failure is displayed even when its preview is ready", async () => {
  api.get.mockResolvedValue({ data: { ...paidPreview, full_report_status: "failed", full_report_error: "Source missing" } });
  mount(); await flush();
  expect(toast.error).toHaveBeenCalledWith("Source missing");
  expect(toast.success).not.toHaveBeenCalled();
});

test("transient connection failure does not claim completion or discard the active job", async () => {
  api.get.mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ data: paidPreview });
  mount(); await flush();
  expect(localStorage.getItem(KEY)).not.toBeNull();
  await act(async () => { jest.advanceTimersByTime(5000); });
  expect(screen.getByTestId("bg-analysis-tracker")).toBeInTheDocument();
  expect(toast.success).not.toHaveBeenCalled();
});

test("expired session stops polling with an accurate sign-in message", async () => {
  api.get.mockRejectedValue(Object.assign(new Error("unauthorized"), { response: { status: 401 } }));
  mount(); await flush();
  expect(toast.error).toHaveBeenCalledWith("Sign in again to check your analysis.");
  expect(localStorage.getItem(KEY)).toBeNull();
});

test("profile dashboard owns status polling and suppresses the floating duplicate", async () => {
  mount("/dashboard"); await flush();
  expect(api.get).not.toHaveBeenCalled();
  expect(screen.queryByTestId("bg-analysis-tracker")).not.toBeInTheDocument();
});
