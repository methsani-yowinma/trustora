// Mirrors backend Pydantic schemas (backend/app/**/schemas.py).
export type UserRole = "CUSTOMER" | "SME" | "ADMIN";
export type AccountStatus = "ACTIVE" | "SUSPENDED";

/** Localized content: {"en": "...", "si": "..."} — at least one locale present. */
export type LocalizedText = Partial<Record<"en" | "si", string>>;

export type Profile = {
  id: string;
  email: string | null;
  role: UserRole;
  status: AccountStatus;
  full_name: string | null;
  phone: string | null;
  preferred_locale: "en" | "si";
  created_at: string;
};

export type VerificationStatus = "UNVERIFIED" | "PENDING" | "VERIFIED" | "REJECTED";
export type VerificationDecision = "SUBMITTED" | "APPROVED" | "REJECTED";
export type SocialPlatform = "INSTAGRAM" | "FACEBOOK" | "TIKTOK" | "WHATSAPP";
export type PolicyKey = "returns" | "refunds" | "delivery";
export type StorePolicies = Partial<Record<PolicyKey, LocalizedText>>;

export type SocialAccount = {
  id: string;
  platform: SocialPlatform;
  handle: string;
  url: string | null;
  ownership_verified: boolean;
  verified_at: string | null;
};

export type OwnSocialAccount = SocialAccount & { verification_code: string };

export type VerificationSummary = {
  id: string;
  status: VerificationDecision;
  business_reg_number: string;
  registered_name: string;
  submitted_at: string;
  reviewed_at: string | null;
  decision_note: string | null;
};

export type EvidenceProvenance =
  | "VERIFIED_FACT"
  | "SELLER_CLAIM"
  | "CUSTOMER_ALLEGATION"
  | "PUBLIC_EVIDENCE"
  | "AI_ANALYSIS"
  | "PLATFORM_STATISTIC";
export type EvidenceReviewStatus = "PENDING" | "ACCEPTED" | "REJECTED";

export type EvidenceFile = {
  id: string;
  type: string;
  provenance: EvidenceProvenance;
  description: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  sha256: string | null;
  review_status: EvidenceReviewStatus;
  created_at: string;
  download_url: string | null;
  ai_analysis?: AiAnalysis | null;
};

export type Verification = VerificationSummary & { documents: EvidenceFile[] };

export type Sme = {
  id: string;
  slug: string;
  name: string;
  logo_url: string | null;
  description_i18n: LocalizedText | null;
  policies_i18n: StorePolicies;
  contact_email: string | null;
  contact_phone: string | null;
  contact_verified: boolean;
  verification_status: VerificationStatus;
  verified_at: string | null;
  is_published: boolean;
  status: "ACTIVE" | "SUSPENDED";
  created_at: string;
  product_counts: Partial<Record<ProductStatus, number>>;
  social_accounts: OwnSocialAccount[];
  latest_verification: VerificationSummary | null;
};

export type PublicStore = {
  id: string;
  slug: string;
  name: string;
  logo_url: string | null;
  description_i18n: LocalizedText | null;
  policies_i18n: StorePolicies;
  contact_email: string | null;
  contact_phone: string | null;
  contact_verified: boolean;
  verification_status: VerificationStatus;
  verified_at: string | null;
  member_since: string;
  social_accounts: SocialAccount[];
};

export type Category = { id: number; slug: string; name_i18n: LocalizedText };

export type ProductStatus = "ACTIVE" | "HIDDEN" | "REMOVED";
export type AuthenticityStatus = "VERIFIED" | "PARTIALLY_VERIFIED" | "UNVERIFIED" | "CONCERN";
export type ProductImage = { id: string; url: string; sort_order: number };

export type Product = {
  id: string;
  category_id: number;
  name_i18n: LocalizedText;
  description_i18n: LocalizedText | null;
  price_lkr: string;
  stock: number;
  status: ProductStatus;
  authenticity_status: AuthenticityStatus;
  images: ProductImage[];
  created_at: string;
  updated_at: string;
};

export type ProductDetail = Product & { evidence: EvidenceFile[] };

export type PublicProduct = {
  id: string;
  category_id: number;
  name_i18n: LocalizedText;
  description_i18n: LocalizedText | null;
  price_lkr: string;
  in_stock: boolean;
  authenticity_status: AuthenticityStatus;
  images: ProductImage[];
};

export type AdminVerificationItem = VerificationSummary & {
  sme_id: string;
  sme_name: string;
  sme_slug: string;
};

export type AdminVerificationDetail = AdminVerificationItem & {
  sme: Sme;
  documents: EvidenceFile[];
  history: VerificationSummary[];
};

export type AdminSocialAccount = OwnSocialAccount & {
  sme_id: string;
  sme_name: string;
  sme_slug: string;
  created_at: string;
};

// --- Trust (backend/app/trust/schemas.py) ----------------------------------------------
export type TrustLevel = "VERIFIED" | "TRUSTED" | "DEVELOPING" | "CAUTION" | "HIGH_RISK";
export type TrustDimension = "BUSINESS" | "PRODUCT" | "TRANSACTION";

export type TrustScore = {
  overall_score: number;
  level: TrustLevel;
  business_score: number;
  product_score: number;
  transaction_score: number;
  rules_version: string;
  computed_at: string;
};

export type TrustSignal = {
  dimension: TrustDimension;
  kind: "POSITIVE" | "RISK" | "INFO";
  code: string;
  points: number;
  provenance: EvidenceProvenance;
  params: Record<string, unknown>;
  evidence_count: number;
};

export type EvidenceSummary = {
  total: number;
  accepted: number;
  pending: number;
  rejected: number;
  by_provenance: Partial<Record<EvidenceProvenance, number>>;
};

export type TrustHistoryPoint = { at: string; overall_score: number; level: TrustLevel };

export type TrustHistory = {
  days: number;
  baseline: TrustHistoryPoint | null;
  points: TrustHistoryPoint[];
  change: { from_score: number; to_score: number; from_level: TrustLevel; to_level: TrustLevel; days: number } | null;
};

export type Passport = {
  store: {
    id: string;
    slug: string;
    name: string;
    logo_url: string | null;
    description_i18n: LocalizedText | null;
    verification_status: VerificationStatus;
    verified_at: string | null;
    member_since: string;
  };
  trust: TrustScore;
  positive_signals: TrustSignal[];
  risk_signals: TrustSignal[];
  info_signals: TrustSignal[];
  evidence_summary: EvidenceSummary;
  history: TrustHistory;
};

export type TrustSuggestion = { code: string; params: Record<string, unknown> };
export type SmeTrust = Passport & { suggestions: TrustSuggestion[] };

export type AdminEvidenceItem = EvidenceFile & {
  sme_id: string;
  sme_name: string;
  sme_slug: string;
  product_id: string | null;
  product_name_i18n: LocalizedText | null;
  flagged_misleading: boolean;
  review_note: string | null;
};

// --- Commerce (backend/app/orders, backend/app/products/browse.py) -------------------------
export type StoreBadge = {
  id: string;
  slug: string;
  name: string;
  verification_status: VerificationStatus;
  trust_level: TrustLevel | null;
  trust_score: number | null;
};

export type ProductCard = {
  id: string;
  category_id: number;
  name_i18n: LocalizedText;
  price_lkr: string;
  in_stock: boolean;
  authenticity_status: AuthenticityStatus;
  image_url: string | null;
  store: StoreBadge;
};

export type Paged<T> = { items: T[]; total: number; page: number; page_size: number };

export type PublicProductDetail = PublicProduct & { store: StoreBadge; max_quantity: number };

export type StoreCard = {
  id: string;
  slug: string;
  name: string;
  logo_url: string | null;
  description_i18n: LocalizedText | null;
  verification_status: VerificationStatus;
  trust_level: TrustLevel | null;
  trust_score: number | null;
  product_count: number;
};

export type Quote = {
  store: StoreBadge;
  lines: {
    product_id: string;
    name_i18n: LocalizedText;
    image_url: string | null;
    unit_price_lkr: string;
    quantity: number;
    line_total_lkr: string;
    available: boolean;
    in_stock_quantity_ok: boolean;
  }[];
  subtotal_lkr: string;
  delivery: { provider_code: string; fee_lkr: string; eta_days: number };
  total_lkr: string;
  issues: string[];
};

export type OrderStatus =
  | "PLACED"
  | "CONFIRMED"
  | "DISPATCHED"
  | "DELIVERED"
  | "COMPLETED"
  | "CANCELLED"
  | "DELIVERY_FAILED";
export type DeliveryStatus = "PENDING" | "DISPATCHED" | "IN_TRANSIT" | "DELIVERED" | "FAILED";

export type Order = {
  id: string;
  order_number: string;
  status: OrderStatus;
  store: StoreBadge;
  items: { product_id: string; product_name_i18n: LocalizedText; unit_price_lkr: string; quantity: number; line_total_lkr: string }[];
  subtotal_lkr: string;
  delivery_fee_lkr: string;
  total_lkr: string;
  shipping_address: Record<string, string | null>;
  payment: {
    method: "COD" | "MOCK_CARD";
    status: "PENDING" | "PAID" | "REFUNDED";
    amount_lkr: string;
    mock_reference: string | null;
    paid_at: string | null;
    refunded_at: string | null;
  };
  delivery: {
    provider_code: string;
    district: string;
    fee_lkr: string;
    eta_days: number;
    status: DeliveryStatus;
    tracking_ref: string | null;
    estimated_delivery_date: string | null;
    dispatched_at: string | null;
    in_transit_at: string | null;
    delivered_at: string | null;
    failed_at: string | null;
    failure_reason: string | null;
  };
  placed_at: string;
  confirmed_at: string | null;
  dispatched_at: string | null;
  delivered_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancelled_by: "CUSTOMER" | "SME" | "ADMIN" | null;
  cancellation_reason: string | null;
  allowed_actions: string[];
  review: Review | null;
  complaint: ComplaintSummary | null;
};

export type OrderSummary = {
  id: string;
  order_number: string;
  status: OrderStatus;
  store_name: string;
  store_slug: string;
  total_lkr: string;
  item_count: number;
  placed_at: string;
  delivery_status: DeliveryStatus;
};

// --- Reviews & complaints (backend/app/reviews, backend/app/complaints) ---------------------
export type Review = {
  id: string;
  rating: number;
  comment: string | null;
  sme_response: string | null;
  sme_responded_at: string | null;
  created_at: string;
};
export type SmeReview = Review & { order_number: string; ai_sentiment: string | null };
export type ReviewPage = { average: number | null; count: number; distribution: Record<string, number>; items: Review[] };

export type ComplaintCategory =
  | "DELIVERY"
  | "WRONG_PRODUCT"
  | "PRODUCT_AUTHENTICITY"
  | "REFUND"
  | "PAYMENT"
  | "CUSTOMER_SERVICE"
  | "PRODUCT_QUALITY"
  | "OTHER";
export type ComplaintStatus = "SUBMITTED" | "SME_RESPONDED" | "UNDER_REVIEW" | "RESOLVED" | "UPHELD" | "DISMISSED";

export type ComplaintSummary = {
  id: string;
  order_number: string;
  store_name: string;
  category: ComplaintCategory;
  status: ComplaintStatus;
  created_at: string;
  escalated_at: string | null;
};

export type Complaint = {
  id: string;
  order_id: string;
  order_number: string;
  store_name: string;
  store_slug: string;
  category: ComplaintCategory;
  description: string;
  status: ComplaintStatus;
  sme_response: string | null;
  sme_responded_at: string | null;
  escalated_at: string | null;
  resolution_note: string | null;
  decided_at: string | null;
  closed_at: string | null;
  created_at: string;
  evidence: EvidenceFile[];
  allowed_actions: string[];
  ai_analysis?: AiAnalysis | null;
};

export type PublicComplaintSummary = {
  open_allegations: Partial<Record<ComplaintCategory, number>>;
  upheld: Partial<Record<ComplaintCategory, number>>;
  resolved: number;
  dismissed: number;
  total: number;
};

// --- AI (backend/app/ai) ---------------------------------------------------------------------
export type AiAnalysis = {
  id: string;
  kind: "COMPLAINT" | "REVIEW" | "DOCUMENT" | "TRUST_EXPLANATION";
  status: "DONE" | "FAILED" | "SKIPPED";
  model: string;
  output: Record<string, unknown> | null;
  checks: Record<string, "MATCH" | "PARTIAL" | "MISMATCH" | "NOT_FOUND"> | null;
  error_code: string | null;
  created_at: string;
  provenance: "AI_ANALYSIS";
};

export type TrustExplanation = {
  text: string;
  source: "AI" | "TEMPLATE";
  locale: "en" | "si";
  model: string | null;
  rules_version: string;
  generated_at: string;
};
