import React from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";
import AnalysisWaiting, { FootballTips } from "./AnalysisWaiting";
import PrecisionScanOverlay from "./PrecisionScanOverlay";
import PremiumReadyOverlay from "./PremiumReadyOverlay";
import { activityLabel, assetUrl, elapsedLabel, getAnalysisView } from "../lib/analysisProgress.mjs";
import { isFullReportReady } from "../lib/reportReady.mjs";
expect.extend(matchers);

const initial = { id: "selected", is_paid: true, analysis_status: "ready", preview: { brief_summary: "Initial preview" },
  player_details: { player_name: "Orman02", age: 11, position: "Winger" }, taps_received: 11,
  created_at: "2026-10-08T15:00:00Z" };
beforeEach(() => { jest.useFakeTimers(); jest.setSystemTime(new Date("2026-10-08T15:02:00Z")); });
afterEach(() => { cleanup(); jest.useRealTimers(); });

test("paid initial preview stays in the waiting room and does not claim full readiness", () => {
  render(<AnalysisWaiting status={initial} onOpenReport={jest.fn()} />);
  expect(screen.getByTestId("analysis-waiting")).toHaveAttribute("data-phase", "queued");
  expect(screen.getByRole("heading", { name: /report is on its way/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Open full report" })).not.toBeInTheDocument();
  expect(screen.getByText("11 player marks received", { exact: false })).toBeInTheDocument();
  expect(screen.queryByText(/taps verified|identity locked|top speed|Scout Assigned|Writing Notes/i)).not.toBeInTheDocument();
});

test("long waits only change elapsed time and tips, never progress, ratings or task completion", () => {
  render(<AnalysisWaiting status={{ ...initial, full_report_status: "generating", full_pipeline_stage: "sequence_model_start" }} />);
  act(() => { jest.advanceTimersByTime(10 * 60_000); });
  expect(screen.getByTestId("analysis-waiting")).toHaveAttribute("data-phase", "analyzing");
  expect(screen.getByTestId("analysis-waiting").querySelector(".analysis-elapsed")).toHaveTextContent("Elapsed 12:00");
  expect(screen.getByRole("list", { name: "Analysis stages" }).querySelector('[data-state="active"]')).toHaveTextContent("Analyze play");
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  expect(screen.queryByText(/\d+%|sec left|almost there|calculated|potential/i)).not.toBeInTheDocument();
});

test("a stored body under finalization waits; saved ready report exposes the open button", () => {
  const open = jest.fn();
  const { rerender } = render(<AnalysisWaiting status={{ ...initial, has_full_report: true, full_report_status: "finalizing" }} onOpenReport={open} />);
  expect(screen.getByTestId("analysis-waiting")).toHaveAttribute("data-phase", "finalizing");
  expect(screen.queryByRole("button", { name: "Open full report" })).not.toBeInTheDocument();
  rerender(<AnalysisWaiting status={{ ...initial, has_full_report: true, full_report_status: "ready" }} onOpenReport={open} />);
  fireEvent.click(screen.getByRole("button", { name: "Open full report" }));
  expect(open).toHaveBeenCalledTimes(1);
  expect(screen.queryByTestId("analysis-football-tips")).not.toBeInTheDocument();
});

test.each([
  { ...initial },
  { ...initial, full_report_status: "ready", has_full_report: false },
  { ...initial, full_report_status: "finalizing", full_report: { scores: {} } },
])("premium celebration rejects incomplete report %#", status => {
  render(<PremiumReadyOverlay open report={status} />);
  expect(screen.queryByTestId("premium-ready-overlay")).not.toBeInTheDocument();
});

test("free completion is explicitly a preview", () => {
  render(<AnalysisWaiting status={{ ...initial, is_paid: false }} onOpenReport={jest.fn()} />);
  expect(screen.getByRole("button", { name: "Open preview" })).toBeInTheDocument();
  expect(screen.queryByText(/full report is ready/i)).not.toBeInTheDocument();
});

test("only measured upload has a percentage and it is scoped to uploading", () => {
  const props = { open: true, playerName: "Orman02", tapsCount: 11, startedAt: Date.now() };
  const { rerender } = render(<PrecisionScanOverlay {...props} phase="uploading" uploadPct={43} />);
  expect(screen.getByRole("progressbar", { name: "Video upload" })).toHaveAttribute("aria-valuenow", "43");
  expect(screen.getByRole("progressbar", { name: "Video upload" })).toHaveTextContent("43% uploaded");
  rerender(<PrecisionScanOverlay {...props} phase="saving" uploadPct={100} />);
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Saving your video" })).toBeInTheDocument();
});

test("tips cycle, pause and move manually without becoming report findings", () => {
  render(<FootballTips />);
  expect(screen.getByRole("heading")).toHaveTextContent("See the space");
  act(() => { jest.advanceTimersByTime(25000); });
  expect(screen.getByRole("heading")).toHaveTextContent("Give your next move");
  fireEvent.click(screen.getByRole("button", { name: "Pause football tips" }));
  act(() => { jest.advanceTimersByTime(50000); });
  expect(screen.getByRole("heading")).toHaveTextContent("Give your next move");
  fireEvent.click(screen.getByRole("button", { name: "Previous football tip" }));
  expect(screen.getByRole("heading")).toHaveTextContent("See the space");
  expect(screen.getByTestId("analysis-football-tips")).toHaveTextContent("Separate from your video analysis.");
});

test("stale heartbeat states uncertainty; it does not guarantee worker recovery", () => {
  render(<AnalysisWaiting status={{ ...initial, last_progress_at: "2026-10-08T14:40:00Z" }} />);
  expect(screen.getByTestId("analysis-server-status")).toHaveTextContent("No recent server update");
  expect(screen.queryByText(/resumes automatically|nothing is lost/)).not.toBeInTheDocument();
});

test("connection errors show rechecking without changing the phase", () => {
  render(<AnalysisWaiting status={{ ...initial, full_report_status: "verifying", has_full_report: true }} connectionError="Connection interrupted. Rechecking the status." />);
  expect(screen.getByTestId("analysis-waiting")).toHaveAttribute("data-phase", "verifying");
  expect(screen.getByTestId("analysis-server-status")).toHaveTextContent("Connection interrupted");
});

test("retry starts only through an explicit button; stalled check is read-only", () => {
  const retry = jest.fn(), check = jest.fn();
  const { rerender } = render(<AnalysisWaiting status={{ ...initial, full_report_status: "failed" }} onRetry={retry} onCheckStatus={check} />);
  expect(retry).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Check status again" }));
  expect(check).toHaveBeenCalledTimes(1); expect(retry).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Retry analysis" })); expect(retry).toHaveBeenCalledTimes(1);
  rerender(<AnalysisWaiting status={{ ...initial, full_report_status: "generating" }} error={{ message: "No recent progress", kind: "stalled" }} onRetry={retry} onCheckStatus={check} />);
  expect(screen.queryByRole("button", { name: "Retry analysis" })).not.toBeInTheDocument();
});

test("video replay is the uploaded video, opened on demand without autoplay", () => {
  const { container } = render(<AnalysisWaiting status={{ ...initial, video_url: "https://media.example/selected.mp4", poster_url: "https://media.example/selected.jpg" }} assetBase="https://app.example" />);
  expect(container.querySelector("img")).toHaveAttribute("src", "https://media.example/selected.jpg");
  expect(container.querySelector("video")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Watch your uploaded video" }));
  expect(container.querySelector("video")).toHaveAttribute("src", "https://media.example/selected.mp4");
  expect(container.querySelector("video")).not.toHaveAttribute("autoplay");
});

test("old stored reports stay readable, but status alone never proves a report exists", () => {
  expect(isFullReportReady({ full_report_status: "ready", has_full_report: false })).toBe(false);
  expect(isFullReportReady({ full_report: { scores: {} } })).toBe(true);
  expect(isFullReportReady({ has_full_report: true, full_report_status: "failed" })).toBe(false);
});

test("invalid clocks and heartbeats are not substituted with made-up timing", () => {
  expect(elapsedLabel("invalid")).toBeNull();
  expect(elapsedLabel(Date.now() + 10000)).toBeNull();
  expect(activityLabel("2099-01-01")).toBe("Waiting for a server update");
  expect(assetUrl("blob:local", "https://app.example")).toBe("blob:local");
  expect(assetUrl("/api/uploads/poster.jpg", "https://app.example")).toBe("https://app.example/api/uploads/poster.jpg");
});

test.each(["generating", "awaiting_confirmation", "verifying", "finalizing", "failed"])("%s cannot be promoted by a partial body or preview", full_report_status => {
  expect(getAnalysisView({ ...initial, full_report_status, has_full_report: true }).complete).toBe(false);
});
