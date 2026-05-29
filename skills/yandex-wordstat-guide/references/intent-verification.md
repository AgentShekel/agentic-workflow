# Intent Verification Guide

Before marking a query as "target", verify what the searcher actually wants to buy.

## Verification Process

For every promising query, answer:
1. What does the person want to buy? (not just "what are they interested in")
2. Will they buy our product from this search?
3. Or are they looking for something adjacent/complementary?

Run WebSearch to check:
```
WebSearch: "каолиновая вата для дымохода" что ищут покупатели
```

Look at results: what products appear, what questions people ask, informational vs transactional intent.

## Red Flags (likely not target)

- Query contains "для [your product]" — they need an accessory, not your product
- Query about materials/components — they DIY, not buy finished product
- Query has "своими руками", "как сделать" — informational, not buying
- Query about repair/maintenance — they already own it

## Examples

| Query | Looks like | Actually | Target? |
|-------|------------|----------|---------|
| каолиновая вата для дымохода | chimney buyer | cotton wool buyer | no |
| дымоход купить | chimney buyer | chimney buyer | yes |
| утепление дымохода | chimney buyer | insulation DIYer | no |
| дымоход сэндвич цена | chimney buyer | chimney buyer | yes |
| потерпевший дтп | lawyer client | news reader | no |
| юрист после дтп | lawyer client | lawyer client | yes |

## Workflow

1. Find queries in Wordstat
2. WebSearch each promising query to verify intent
3. Mark as target only if intent matches the sale
4. Report both target and rejected queries with reasoning
