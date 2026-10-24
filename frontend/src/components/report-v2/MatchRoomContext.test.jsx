import React from "react";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { MatchRoomContext } from "./MatchRoomContext";
import { SkillMeaningCard } from "./scoremeaning";

jest.mock("./sections", () => ({ V2Card: ({ children }) => <div>{children}</div> }));

const skill = { key: "control", category: "technical", label: "Ball control", score: 8,
  lines: ["Protects the ball under pressure."],
  evidence: { verified: true, proof_verified: true, timestamp: "00:10", event_id: "event-1" } };
beforeEach(() => {
  jest.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  jest.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  jest.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
});
afterEach(() => { cleanup(); jest.restoreAllMocks(); });

test("skill proof opens the contextual player without the floating handler", () => {
  const open = jest.fn(), floating = jest.fn();
  render(<MatchRoomContext.Provider value={{ open, proof: null }}>
    <SkillMeaningCard s={skill} authority onPlayAt={floating} />
  </MatchRoomContext.Provider>);
  fireEvent.click(screen.getByTestId("sm-evidence-control"));
  expect(open).toHaveBeenCalledWith("control", "00:10", { evidenceId: undefined, eventId: "event-1" });
  expect(floating).not.toHaveBeenCalled();
});

test("one selected skill owns the inline clip; controls operate on clip-local time", () => {
  const room = { open: jest.fn(), close: jest.fn(), proof: { skillKey: "control", ts: "00:10", clip: "/proof.mp4", clipStart: 8, key: "proof-1" } };
  render(<MatchRoomContext.Provider value={room}>
    <SkillMeaningCard s={skill} authority />
    <SkillMeaningCard s={{ ...skill, key: "touch" }} authority />
  </MatchRoomContext.Provider>);
  const video = screen.getByTestId("proof-clip-video");
  expect(document.querySelectorAll("video")).toHaveLength(1);
  expect(video.autoplay).toBe(false);
  expect(video.loop).toBe(false);
  expect(screen.getByTestId("proof-player-sheet").className).not.toContain("fixed");
  fireEvent.click(screen.getByText("Slow motion · 0.5×"));
  expect(video.playbackRate).toBe(0.5);
  Object.defineProperty(video, "readyState", { configurable: true, value: 4 });
  fireEvent.click(screen.getByText("Inspect the moment"));
  expect(video.currentTime).toBe(2);
  fireEvent.click(screen.getByTestId("proof-player-close"));
  expect(room.close).toHaveBeenCalledTimes(1);
});

test("unverified authority evidence does not offer Match Room navigation", () => {
  render(<MatchRoomContext.Provider value={{ open: jest.fn(), proof: null }}>
    <SkillMeaningCard s={{ ...skill, evidence: { ...skill.evidence, proof_verified: false } }} authority />
  </MatchRoomContext.Provider>);
  expect(screen.queryByTestId("sm-evidence-control")).toBeNull();
});

test("a failed proof clip falls back to the original at the source timestamp, paused", () => {
  const room = { open: jest.fn(), close: jest.fn(), videoUrl: "/original.mp4",
    proof: { skillKey: "control", ts: "00:10", clip: "/proof.mp4", clipStart: 8, key: "fallback" } };
  render(<MatchRoomContext.Provider value={room}><SkillMeaningCard s={skill} authority /></MatchRoomContext.Provider>);
  fireEvent.error(screen.getByTestId("proof-clip-video"));
  const video = screen.getByTestId("proof-player-video");
  Object.defineProperty(video, "readyState", { configurable: true, value: 4 });
  fireEvent.loadedMetadata(video);
  expect(video.currentTime).toBe(6);
  expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Inspect the moment"));
  expect(video.currentTime).toBe(10);
  expect(document.querySelectorAll("video")).toHaveLength(1);
});
