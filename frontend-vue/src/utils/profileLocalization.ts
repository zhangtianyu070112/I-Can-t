const exactTranslations: Record<string, string> = {
  'beginner to intermediate': '初学到中等水平',
  'overlooking fundamentals, asking for self-introduction repeatedly': '容易忽视基础知识，并重复询问自我介绍相关问题',
  'text with examples': '文字讲解结合实例',
  'slower, step-by-step': '较慢节奏，适合分步骤学习',
  'external guidance + achievement-oriented': '外部指导与成就目标驱动型',
  'self-introduction confusion': '自我介绍相关概念易混淆',
  'resource dissatisfaction': '对当前学习资源不满意',
  'needs step-by-step guidance': '需要分步骤指导',
  'java learning': 'Java 学习',
  fundamental: '基础知识',
  'self-introduction': '自我介绍',
}

const phraseTranslations: Array<[RegExp, string]> = [
  [/\bbeginner\s+to\s+intermediate\b/gi, '初学到中等水平'],
  [/\bself[- ]introduction\s+confusion\b/gi, '自我介绍相关概念易混淆'],
  [/\bself[- ]introduction\b/gi, '自我介绍'],
  [/\bresource\s+dissatisfaction\b/gi, '对当前学习资源不满意'],
  [/\bneeds?\s+step[- ]by[- ]step\s+guidance\b/gi, '需要分步骤指导'],
  [/\bstep[- ]by[- ]step\b/gi, '分步骤'],
  [/\boverlooking\s+fundamentals\b/gi, '容易忽视基础知识'],
  [/\btext\s+with\s+examples\b/gi, '文字讲解结合实例'],
  [/\bexternal\s+guidance\b/gi, '外部指导'],
  [/\bachievement[- ]oriented\b/gi, '成就目标驱动型'],
  [/\bjava\s+learning\b/gi, 'Java 学习'],
  [/\bfundamentals?\b/gi, '基础知识'],
]

export function localizeProfileText(value: unknown): string {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  const exact = exactTranslations[text.toLowerCase()]
  if (exact) return exact
  let localized = text.replace(/_/g, ' ')
  for (const [pattern, replacement] of phraseTranslations) localized = localized.replace(pattern, replacement)
  const residual = localized.replace(/\b(?:Java|UML|SQL|JDBC|HTTP|TCP|UDP|API|I\/O|C\+\+|C)\b/gi, '')
  if (/[A-Za-z]{2,}/.test(residual)) {
    const chineseOnly = localized
      .replace(/\b[A-Za-z][A-Za-z0-9+./-]*\b/g, '')
      .replace(/\s*[,;+]\s*/g, '，')
      .replace(/\s+/g, ' ')
      .replace(/^[ ，、+-]+|[ ，、+-]+$/g, '')
    return /[\u4e00-\u9fff]/.test(chineseOnly) ? chineseOnly : '已识别的学习特征'
  }
  return localized
}

export function localizeProfileOverview<T extends Record<string, any>>(profile: T): T {
  return {
    ...profile,
    learner: {
      ...(profile.learner || {}),
      major: localizeProfileText(profile.learner?.major),
      current_course: localizeProfileText(profile.learner?.current_course),
    },
    dimensions: (profile.dimensions || []).map((item: Record<string, any>) => ({
      ...item,
      value: localizeProfileText(item.value),
      description: localizeProfileText(item.description),
    })),
    focus: {
      ...(profile.focus || {}),
      weak_points: (profile.focus?.weak_points || []).map(localizeProfileText),
      keywords: (profile.focus?.keywords || []).map(localizeProfileText),
      headline: localizeProfileText(profile.focus?.headline),
    },
    history: (profile.history || []).map((item: Record<string, any>) => ({
      ...item,
      reason: localizeProfileText(item.reason),
    })),
    comparison: {
      ...(profile.comparison || {}),
      changes: (profile.comparison?.changes || []).map((item: Record<string, any>) => ({
        ...item,
        before: localizeProfileText(item.before),
        after: localizeProfileText(item.after),
      })),
    },
  } as T
}
