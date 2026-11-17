# Personal Chinese Translation Style

This is the owner's Chinese-language preference. Apply it to Simplified or Traditional Chinese catalogs selected by the project; keep it out of locale-neutral engine logic.
Other locales define their own punctuation policy.

## Required sentence-ending rule

故事文本、人物对话以外的文本里，只要一句话中间没有逗号和顿号，这个句子的最后就不要加句号。

Operational interpretation:

1. Classify by content, not resource name. `story` and `dialogue` are exempt; `other` follows this rule. Resolve `unknown` before approval.
2. Judge each sentence separately, not an entire record, paragraph or file.
3. A comma means `，` or `,`; an enumeration comma means `、`.
4. If a sentence contains none of these marks, omit its final full stop `。` (and an ASCII `.` when it really functions as a sentence-ending full stop).
5. A comma/enumeration comma permits the normal style decision; it does not require adding a final full stop.
6. Preserve question marks, exclamation marks and ellipses. Keep decimal points, versions, paths, extensions and other non-sentence dots intact.
7. Ignore verified invisible control/formatting tokens when finding the visible sentence ending; preserve the tokens themselves.
8. A closing quote/bracket after a full stop does not hide the full stop from this rule. A colon or semicolon does not count as a comma.

The rule follows logical sentences, not layout lines. A newline or ellipsis alone does not prove that a new sentence begins; preserve both without discarding a comma earlier in the same sentence. Independent messages/ellipsis-ended sentences must be separated into verified spans when context establishes that boundary.
The plain-text checker treats `。！？!?` and clear ASCII sentence-ending periods at the current quote/bracket depth as boundaries. Punctuation in a nested quote does not reset its enclosing sentence. Commas in a completed preceding sentence do not exempt the next one.
Mixed narrative/UI content requires role-specific spans. Ambiguous quotation or dot semantics require contextual review rather than global deletion.

## Examples

| Role | Before | Result |
|---|---|---|
| other | 保存成功。 | 保存成功 |
| other | 请选择一个存档。 | 请选择一个存档 |
| other | 提高攻击力；持续十秒。 | 提高攻击力；持续十秒 |
| other | 保存完成，请继续。 | 保存完成，请继续。 |
| other | 获得药草、铁矿石。 | 获得药草、铁矿石。 |
| other | 保存完成，请继续。按键返回。 | 保存完成，请继续。按键返回 |
| other | 「保存成功。」 | 「保存成功」 |
| other | 是否覆盖？ | 是否覆盖？ |
| other | 正在加载…… | 正在加载…… |
| other | 版本 1.2.3 | 版本 1.2.3 |
| other | 保存完成，〈换行〉请继续。 | 保留句号；换行属于同一句的排版 |
| other | 保存完成，请稍候……然后继续。 | 保留句号；省略号属于同一句 |
| other | 请确认，选择“成功！”按钮。 | 保留末尾句号；内层感叹号不切断外层句子 |
| story | 夜色渐深。 | 夜色渐深。 |
| dialogue | 我马上回来。 | 我马上回来。 |

System/tutorial/item-description text normally uses `other`; a lore passage or spoken tutorial line may instead be story/dialogue according to actual content.
Do not insert unnecessary commas merely to retain a final full stop.

## Reference check and limits

The included catalog validator reports offending full stops in plain display text without changing files.
It reports definite full-stop violations as `zh_sentence_ending`. Ambiguous numeric/ASCII-word terminal dots (including possible abbreviations), unmatched quotes and detected markup-like input produce `zh_style_review`; both are unresolved findings, not a pass. Internal decimal/version/filename dots remain intact.
It does not understand arbitrary game markup or every quotation grammar. Common quote pairs are tracked, but a project adapter must expose verified visible sentences and add fixtures for its own syntax.
Resolve ambiguous cases in context and record the decision in the project adapter/review evidence; do not convert a review finding into an automatic deletion. The reference CLI intentionally has no blanket suppression option.

## Project-specific decisions

Terminology is maintained in [glossary.json](glossary.json). Project role mapping, CP1252 source fingerprints and verified native token projection are documented in [PROJECT_CONTRACT](../../docs/PROJECT_CONTRACT.md). The current narrative category combines story/dialogue and has not been re-reviewed record by record. No new per-ID punctuation exceptions were approved during baseline adoption.

Preserve the rule above unless the owner explicitly changes it; record any approved exception by string ID and reason. The project checker and build gate use this rule; unresolved findings remain failures, not release allowlists.

The generated [policy review queue](policy-review.json) records unresolved findings and target fingerprints; it grants no exceptions.

README and project-document explanatory prose do not follow the game-text sentence-ending rule. Quoted translations still do; label deliberately incorrect/before examples clearly. The earlier documentation-only migration is retained in [MIGRATION](../../docs/MIGRATION.md); current checker evidence is in [adoption validation](../../docs/ADOPTION_VALIDATION.md).
