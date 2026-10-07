// Mirrors backend/app/deliveries/provider.py. Names are translated via messages "districts.*".
export const DISTRICTS = [
  "COLOMBO", "GAMPAHA", "KALUTARA", "KANDY", "MATALE", "NUWARA_ELIYA", "GALLE", "MATARA",
  "HAMBANTOTA", "JAFFNA", "KILINOCHCHI", "MANNAR", "VAVUNIYA", "MULLAITIVU", "BATTICALOA",
  "AMPARA", "TRINCOMALEE", "KURUNEGALA", "PUTTALAM", "ANURADHAPURA", "POLONNARUWA", "BADULLA",
  "MONERAGALA", "RATNAPURA", "KEGALLE",
] as const;

export type District = (typeof DISTRICTS)[number];
