import type { RuleSummary, WorldTemplateSummary } from '@/api/types'

/** 世界模板推荐规则 → 当前可用规则摘要；缺失/不存在的推荐项直接忽略。 */
export function recommendedRuleSummaries(
  template: WorldTemplateSummary | undefined,
  rules: RuleSummary[],
): RuleSummary[] {
  const ids = template?.recommended_rules
  if (!Array.isArray(ids)) return []
  const seen = new Set<string>()
  const result: RuleSummary[] = []
  for (const id of ids) {
    const ruleId = String(id || '').trim()
    if (!ruleId || seen.has(ruleId)) continue
    const found = rules.find(item => item.rule_id === ruleId)
    if (found) {
      seen.add(ruleId)
      result.push(found)
    }
  }
  return result
}
