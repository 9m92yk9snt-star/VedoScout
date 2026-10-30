import React, { createContext, useContext } from "react";
import { ProofPlayerSheet } from "./proofplayer";
import { MatchRoomPlayer } from "./MatchRoomPlayer";

// One selected skill, one player. All media still comes from the report's
// existing authority join; no prototype scores, annotations or sample clips.
export const MatchRoomContext = createContext(null);

export function SkillMatchRoom({ skillKey, skill }) {
  const room = useContext(MatchRoomContext);
  if (!room || room.proof?.skillKey !== skillKey) return null;
  if (!room.demo && !room.proof.locked) return <MatchRoomPlayer key={room.proof.key} proof={room.proof} skill={skill} videoUrl={room.videoUrl} posterUrl={room.posterUrl} onClose={room.close} />;
  return <ProofPlayerSheet inline proof={room.proof} videoUrl={room.videoUrl}
    posterUrl={room.posterUrl} frames={room.frames} demo={room.demo} onClose={room.close} />;
}
