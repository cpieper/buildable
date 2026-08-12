# Buildable Candidate Discovery Design

## Goal

Make the Buildable Sets page easier to understand and seed with useful candidates by including owned sets by default, clarifying catalog import language, and guiding users when no buildable results appear.

## Decisions

Buildable Sets should evaluate the app's local catalog candidate pool, not imply that it imports the user's owned collection. Catalog import copy will describe "set references and inventories for matching" so it is distinct from collection CSV import.

Owned sets should appear in Buildable Sets by default. A top-level "Include owned sets" toggle will be on initially and will map to the existing recommendations API by sending `hide_owned=false`. Turning it off sends `hide_owned=true` and narrows results to sets not already in the collection.

When Buildable Sets has no results, the page should explain why matching may be empty and give clear next actions: add owned sets, import a Rebrickable catalog ZIP, add a catalog set manually, search/import a specific target when an API key is configured, or broaden filters such as missing-piece matches and maximum pieces.

## Scope

This change affects the recommendations page UI and Settings catalog import wording. It does not add a background crawler, scheduled sync, broad remote import, or a new recommendation algorithm. Candidate expansion remains local-first: broad coverage comes from ZIP import, and targeted expansion comes from Rebrickable search/lookup or manual catalog entry.

## Data Flow

The frontend owns the new default by initializing `includeOwned=true`, serializing it in the URL, and calling `/api/recommendations` with `hide_owned=false`. The existing backend parameter and SQL filter already support this. Recommendation rows can continue using the existing response shape because the presence of owned sets is controlled by the request, not by per-row metadata.

## Testing

Frontend tests should prove the default request includes owned sets, the toggle can exclude them, the URL preserves the setting, empty results show guidance, and Settings copy distinguishes catalog candidates from collection import. Existing API recommendation tests already cover `hide_owned=false`.
