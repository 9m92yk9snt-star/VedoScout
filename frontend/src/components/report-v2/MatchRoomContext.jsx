import React, { createContext, useContext } from "react";
import { ProofPlayerSheet } from "./proofplayer";

// One selected skill, one player. All media still comes from the report's
// existing authority join; no prototype scores, annotations or sample clips.
export const MatchRoomContext = createContext(null);

export function SkillMatchRoom({ skillKey }) {
  const room = useContext(MatchRoomContext);
  if (!room || room.proof?.skillKey !== skillKey) return null;
  return <ProofPlayerSheet inline proof={room.proof} videoUrl={room.videoUrl}
    posterUrl={room.posterUrl} frames={room.frames} demo={room.demo} onClose={room.close} />;
}
