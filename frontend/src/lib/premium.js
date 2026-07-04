// Single source of truth for "is this user a paid/premium tier?".
// Premium can come from EITHER a privileged role OR an active subscription
// (admin-granted Premium/VIP users keep role="user" with subscription_tier set).
export const PREMIUM_ROLES = ["admin", "premium", "vip", "scout"];

export function isPremiumUser(user) {
  if (!user) return false;
  if (PREMIUM_ROLES.includes(user.role)) return true;
  return ["premium", "vip"].includes(user.subscription_tier);
}
