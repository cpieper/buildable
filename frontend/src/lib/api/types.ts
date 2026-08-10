export interface SessionResponse { authenticated: boolean; }
export interface ApiProblem { detail?: string; message?: string; code?: string; }
export interface CatalogSetSummary { set_num: string; name: string; year: number | null; theme_name: string | null; num_parts: number; image_url: string | null; has_local_overrides: boolean; }
export interface CatalogPart { part_num: string; part_name: string; color_id: number; color_name: string; rgb_hex: string; quantity: number; is_spare: boolean; source_kind: string; image_url: string | null; }
export interface CatalogSetDetail extends CatalogSetSummary { external_url: string | null; instructions_url: string | null; parts: CatalogPart[]; }
export interface OwnedSet { id: number; set_num: string; set_name: string; quantity: number; completeness: 'complete' | 'incomplete'; unknown_missing_count: number; unknown_missing_note: string | null; notes: string | null; known_missing_total: number; has_local_overrides: boolean; added_at: string; updated_at: string; }
export interface MissingPart { id: number; owned_set_id: number; part_num: string; color_id: number; quantity: number; note: string | null; }
export interface InventoryItem { part_num: string; part_name: string; color_id: number; color_name: string; rgb_hex: string; quantity: number; image_url: string | null; source_set_nums: string[]; }
export interface InventoryWarning { owned_set_id: number; set_num: string; set_name: string; unknown_missing_count: number | null; note: string | null; }
export interface InventoryResponse { items: InventoryItem[]; warnings: InventoryWarning[]; total_quantity: number; }
export type MatchStatus = 'exact' | 'substitution' | 'missing';
export interface MatchCounts { required: number; exact: number; color_substitution: number; equivalence_substitution: number; missing: number; }
export interface Recommendation { set_num: string; name: string; year: number | null; theme_name: string | null; num_parts: number; image_url: string | null; has_local_overrides: boolean; status: MatchStatus; counts: MatchCounts; percent_exact: number; percent_buildable: number; }
export interface RecommendationsResponse { items: Recommendation[]; total_candidates: number; offset: number; limit: number; max_pieces: number; theme: string | null; year_from: number | null; year_to: number | null; hide_owned: boolean; status: MatchStatus[] | null; sort: 'buildability' | 'pieces' | 'year' | 'mismatches' | 'missing'; direction: 'asc' | 'desc'; }
export interface MatchPart { part_num: string; name: string; image_url: string | null; }
export interface MatchColor { id: number; name: string; rgb_hex: string; }
export interface Substitution { required_part: MatchPart; required_color: MatchColor; supplied_part: MatchPart; supplied_color: MatchColor; quantity: number; kind: 'color' | 'equivalent_exact_color' | 'equivalent_color'; }
export interface MissingRequirement { part_num: string; part_name: string; color_id: number; color_name: string; quantity: number; }
export interface MatchDetail extends Recommendation { external_url: string | null; instructions_url: string | null; substitutions: Substitution[]; missing: MissingRequirement[]; warnings: InventoryWarning[]; }
