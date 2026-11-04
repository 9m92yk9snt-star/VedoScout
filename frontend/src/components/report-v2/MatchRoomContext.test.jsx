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
  const video = screen.getByTestId("match-room-video");
  expect(document.querySelectorAll("video")).toHaveLength(1);
  expect(video.autoplay).toBe(false);
  expect(video.loop).toBe(false);
  expect(screen.getByTestId("match-room").className).not.toContain("fixed");
  fireEvent.click(screen.getByText("1×"));
  expect(video.playbackRate).toBe(0.5);
  Object.defineProperty(video, "readyState", { configurable: true, value: 4 });
  fireEvent.loadedMetadata(video);
  expect(video.currentTime).toBe(0);
  fireEvent.click(screen.getByLabelText("Continue"));
  fireEvent.play(video);
  Object.defineProperty(video, "paused", { configurable: true, value: false });
  video.currentTime=2.1;
  fireEvent.timeUpdate(video);
  expect(video.currentTime).toBe(2);
  fireEvent.seeked(video);
  expect(screen.getByText("Take a moment · continue when ready")).toBeTruthy();
  fireEvent.click(screen.getByLabelText("Close Match Room"));
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
  fireEvent.error(screen.getByTestId("match-room-video"));
  const video = screen.getByTestId("match-room-video");
  Object.defineProperty(video, "readyState", { configurable: true, value: 4 });
  fireEvent.loadedMetadata(video);
  expect(video.currentTime).toBe(6);
  expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  fireEvent.click(screen.getByLabelText("Continue"));
  fireEvent.play(video);
  Object.defineProperty(video, "paused", { configurable: true, value: false });
  video.currentTime=10.1;
  fireEvent.timeUpdate(video);
  expect(video.currentTime).toBe(10);
  expect(document.querySelectorAll("video")).toHaveLength(1);
});
