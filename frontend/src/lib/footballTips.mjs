// General coaching ideas only. Never observations about the uploaded player.
export const FOOTBALL_TIPS = [
  ["Awareness", "See the space before the ball arrives", "Check your shoulder before receiving. Let your first touch take you away from pressure.", "scan"],
  ["First touch", "Give your next move a head start", "Open your body to the pitch. Receive into space so your next action stays simple.", "touch"],
  ["Movement", "Pass, then change the picture", "Move to a new angle after passing. Give your teammate another clear option.", "pass"],
  ["Finishing", "Pick your corner early", "Practise accurate finishes first. Add speed and pressure once the placement feels repeatable.", "shot"],
  ["Defending", "Stay balanced. Show them wide.", "Slow down as you approach. Protect the dangerous space before trying to win the ball.", "defend"],
  ["Dribbling", "A small touch. A big change.", "Keep the ball close near pressure, then accelerate into the space your move creates.", "dribble"],
  ["Teamwork", "Make your voice useful", "A clear ‘time’, ‘turn’ or ‘man on’ can help a teammate before the ball arrives.", "pass"],
  ["Mindset", "Win your next action", "After a mistake, find one useful job: recover, offer support or close a passing lane.", "recover"],
  ["Passing", "Play to their next step", "Look at your teammate’s movement. Aim the pass where they can keep moving.", "pass"],
  ["Awareness", "Look again as the ball travels", "The picture changes quickly. A second glance can reveal a better option.", "scan"],
  ["Receiving", "Meet the ball with a plan", "Decide what you might do before receiving, then adjust if the defender moves.", "touch"],
  ["Movement", "Arrive in space. Don’t wait in it.", "Time your movement so the passing lane opens as your teammate looks up.", "run"],
  ["1 v 1", "Move the defender first", "A body feint can create a small opening. Change pace when you attack it.", "dribble"],
  ["Finishing", "Follow your finish", "Stay alert after a shot. A rebound may offer the next chance.", "shot"],
  ["Defending", "Protect the inside route", "Check the space behind you. Angle your approach to make the direct route harder.", "defend"],
  ["Support", "Build a passing triangle", "Find a different angle from the nearest teammate. Two options help the ball carrier.", "pass"],
  ["First touch", "Let the far foot help", "When pressure allows, practise receiving across your body to see more of the pitch.", "touch"],
  ["Transition", "React when possession changes", "When the ball is lost, check whether to press, recover or cover a teammate.", "recover"],
  ["Communication", "Point out the next option", "Use a simple gesture as well as your voice. Help teammates see the space you see.", "scan"],
  ["Training", "Make the target smaller", "Challenge your passing accuracy with a small gate. Widen it if technique starts to break down.", "pass"],
  ["Awareness", "Find the free teammate", "Before carrying forward, check whether a teammate already has more space.", "scan"],
  ["Wing play", "Change the angle of the attack", "A pass inside and a new outside run can open a route around a defender.", "run"],
  ["Dribbling", "Keep your eyes in the game", "Practise short glances up between touches so you can notice support and pressure.", "dribble"],
  ["First touch", "Cushion the pace", "Practise softening a firm pass before adding your next movement.", "touch"],
  ["Finishing", "Accuracy before power", "Choose a clear target in training. Build power while keeping control of placement.", "shot"],
  ["Defending", "Be patient near the ball", "Stay on your feet when you can. Wait for a loose touch before committing.", "defend"],
  ["Movement", "Create space for someone else", "A well-timed run can pull a defender away, even when you do not receive the pass.", "run"],
  ["Mindset", "Keep the next task small", "Under pressure, focus on one clear action: scan, receive, pass or recover.", "recover"],
  ["Passing", "Match the weight to the space", "A short pass needs enough pace to arrive safely without making the next touch harder.", "pass"],
  ["Teamwork", "Support behind the ball too", "Offer a safe return pass when the forward route is crowded.", "pass"],
  ["Receiving", "Move off the defender’s line", "A small step sideways can turn a blocked passing lane into a useful one.", "touch"],
  ["Awareness", "Check both sides", "Find the defender and your support before the ball reaches you.", "scan"],
  ["Wing play", "Use a stop to create a start", "Changing rhythm can unbalance a defender. Keep control before accelerating again.", "dribble"],
  ["Finishing", "Practise from both sides", "Try controlled finishes from different angles. Let technique lead the session.", "shot"],
  ["Defending", "Cover your teammate’s press", "When a teammate closes the ball, look for the passing lane you can protect.", "defend"],
  ["Movement", "Curve the supporting run", "An angled run can help you stay available while avoiding the defender’s cover.", "run"],
  ["Passing", "Show where you want it", "A clear movement or hand signal can help a teammate find your preferred space.", "pass"],
  ["Transition", "Recover with the game in view", "Look at the ball and nearby runners as you move back into position.", "recover"],
  ["First touch", "Practise with gentle pressure", "Ask a teammate to close you down slowly, then build speed as your control improves.", "touch"],
  ["Confidence", "Notice one thing you learned", "After training, choose one useful improvement to take into your next session.", "scan"],
].map(([category, title, text, visual], id) => ({ id, category, title, text, visual }));

const memory = new Map();
let lastGroup = -1;
export function tipDeck(sessionKey = "upload", storage) {
  try { if (storage === undefined) storage = globalThis.sessionStorage; } catch { storage = null; }
  const key = `scoutme:tips:${sessionKey}`;
  try {
    const existing = storage?.getItem(key);
    if (existing !== null && existing !== undefined && /^[0-3]$/.test(existing)) {
      const group = Number(existing);
      return FOOTBALL_TIPS.slice(group * 10, group * 10 + 10);
    }
  } catch { /* Storage may be disabled. The current page still rotates. */ }
  if (!memory.has(key)) {
    let previous = lastGroup;
    try { previous = Number(storage?.getItem("scoutme:tips:last") ?? lastGroup); } catch { /* optional */ }
    lastGroup = (previous + 1) % 4;
    memory.set(key, lastGroup);
    try { storage?.setItem(key, String(lastGroup)); storage?.setItem("scoutme:tips:last", String(lastGroup)); } catch { /* optional */ }
  }
  const group = memory.get(key);
  return FOOTBALL_TIPS.slice(group * 10, group * 10 + 10);
}
