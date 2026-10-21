import React from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import AnalysisWaiting, { FootballTips } from "./AnalysisWaiting";
import PrecisionScanOverlay from "./PrecisionScanOverlay";
import PremiumReadyOverlay from "./PremiumReadyOverlay";
import { activityLabel, assetUrl, completionLabel, elapsedLabel, getAnalysisView } from "../lib/analysisProgress.mjs";
import { isFullReportReady } from "../lib/reportReady.mjs";
import { FOOTBALL_TIPS, tipDeck } from "../lib/footballTips.mjs";

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

test("a provisional live window never changes ratings or task completion", () => {
  render(<AnalysisWaiting status={{ ...initial, full_report_status: "generating", full_pipeline_stage: "sequence_model_start" }} />);
  act(() => { jest.advanceTimersByTime(10 * 60_000); });
  expect(screen.getByTestId("analysis-waiting")).toHaveAttribute("data-phase", "analyzing");
  expect(screen.getByTestId("analysis-finish-estimate")).toHaveTextContent(/About|Under/);
  expect(screen.getByRole("list", { name: "Analysis stages" }).querySelector('[data-state="active"]')).toHaveTextContent("Reviewing play");
  expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
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
  expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  expect(screen.getByRole("heading", { name: "Saving your video" })).toBeInTheDocument();
});

test("tips change every five seconds, pause, and stay separate from findings", () => {
  render(<FootballTips sessionKey="tips-cycle-test" />);
  const first = screen.getByRole("heading").textContent;
  act(() => { jest.advanceTimersByTime(4999); });
  expect(screen.getByRole("heading").textContent).toBe(first);
  act(() => { jest.advanceTimersByTime(1); });
  const second = screen.getByRole("heading").textContent;
  expect(second).not.toBe(first);
  fireEvent.click(screen.getByRole("button", { name: "Pause football tips" }));
  act(() => { jest.advanceTimersByTime(15000); });
  expect(screen.getByRole("heading").textContent).toBe(second);
  fireEvent.click(screen.getByRole("button", { name: "Previous football tip" }));
  expect(screen.getByRole("heading").textContent).toBe(first);
  expect(screen.getByTestId("analysis-football-tips")).toHaveTextContent("General advice · not report findings");
});

test("four analyses get ten distinct tips each and retain their deck on return", () => {
  const values = new Map();
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const decks = [0, 1, 2, 3].map(i => tipDeck(`deck-test-${i}`, storage));
  expect(FOOTBALL_TIPS).toHaveLength(40);
  expect(new Set(decks.flat().map(tip => tip.id)).size).toBe(40);
  expect(decks.every(deck => deck.length === 10)).toBe(true);
  expect(tipDeck("deck-test-1", storage)).toEqual(decks[1]);
  expect(tipDeck("blocked-storage", { getItem: () => { throw Error("blocked"); }, setItem: () => { throw Error("blocked"); } })).toHaveLength(10);
});

test("server work updates the finish window without changing readiness", () => {
  const now = Date.now();
  const { rerender } = render(<AnalysisWaiting status={initial} />);
  expect(screen.getByTestId("analysis-finish-estimate")).not.toHaveTextContent(/not available/i);
  const status = { ...initial, full_report_status: "generating", completion_estimate: {
    status: "estimated", basis: "completed_workload", provisional: true, calculated_at: new Date(now).toISOString(),
    earliest_at: new Date(now+120000).toISOString(), latest_at: new Date(now+240000).toISOString() } };
  rerender(<AnalysisWaiting status={status} />);
  expect(screen.getByTestId("analysis-finish-estimate")).toHaveTextContent("About 2–4 min");
  expect(screen.getByTestId("analysis-finish-estimate")).toHaveTextContent("Expected finish");
  act(() => { jest.advanceTimersByTime(60000); });
  expect(screen.getByTestId("analysis-finish-estimate")).toHaveTextContent("About 1–3 min");
  expect(screen.getByTestId("analysis-waiting")).toHaveAttribute("data-phase", "queued");
});

test("a numeric upload start has a stable countdown before the first status response", () => {
  const data = { analysis_target: "full", analysis_started_at: Date.now() };
  expect(completionLabel(data, Date.now()+60000)).not.toBe(completionLabel(data, Date.now()));
  const view = getAnalysisView({ ...initial, full_report_status: "generating", sequence_progress: { phase: "writer" } });
  expect(view.title).toBe("Writing your player report");
  expect(view.steps[1].state).toBe("done");
  expect(view.complete).toBe(false);
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
  fireEvent.click(screen.getByRole("button", { name: "Close uploaded video" }));
  expect(container.querySelector("video")).toBeNull();
  expect(screen.getByRole("button", { name: "Watch your uploaded video" })).toHaveFocus();
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

test("an older player-check state continues automatically without a manual instruction", () => {
  const view = getAnalysisView({ ...initial, full_report_status: "awaiting_confirmation" });
  expect(view.confirmation).toBe(false);
  expect(view.complete).toBe(false);
  expect(view.detail).toContain("No extra taps");
});


test("remaining time is a server-backed range, expires and never reaches a fake five-second floor", () => {
  const now = Date.now();
  const data = { ...initial, full_report_status: "generating", full_pipeline_stage: "sequence_model_start", completion_estimate: {status:"estimated", calculated_at:new Date(now).toISOString(), earliest_at:new Date(now+4*60000).toISOString(), latest_at:new Date(now+7*60000).toISOString()} };
  expect(completionLabel(data, now)).toBe("About 4–7 min");
  expect(completionLabel(data, now+121000)).toMatch(/^Last estimate:/);
  expect(completionLabel({...data,completion_estimate:{...data.completion_estimate,calculated_at:new Date(now+8*60000).toISOString()}},now+8*60000)).toBe("Longer than expected · updating");
  render(<AnalysisWaiting status={data} onContinue={jest.fn()} />);
  expect(screen.getByTestId("analysis-finish-estimate")).toHaveTextContent("Estimated time remaining");
  expect(screen.getByTestId("analysis-finish-estimate")).toHaveTextContent("About 4–7 min");
  expect(screen.getByRole("button", {name:"Continue in background"})).toBeInTheDocument();
});

test("background exit is available only after upload acceptance and sends one navigation action", () => {
  const leave=jest.fn();
  const {rerender}=render(<AnalysisWaiting status={initial} phase="uploading" uploadPct={42} onContinue={leave}/>);
  expect(screen.queryByRole("button",{name:"Continue in background"})).not.toBeInTheDocument();
  rerender(<AnalysisWaiting status={initial} onContinue={leave}/>);
  fireEvent.click(screen.getByRole("button",{name:"Continue in background"}));
  expect(leave).toHaveBeenCalledTimes(1);
});


test("stale worker activity suppresses a fresh calculated estimate", () => {
  const now = Date.now();
  const data = { last_progress_at: new Date(now-180000).toISOString(), completion_estimate: { status:"estimated", calculated_at:new Date(now).toISOString(), earliest_at:new Date(now+60000).toISOString(), latest_at:new Date(now+180000).toISOString() } };
  expect(completionLabel(data, now)).toMatch(/^Last estimate:/);
});
