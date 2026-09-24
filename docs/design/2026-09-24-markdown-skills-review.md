# Markdown skills review, 24 September 2026

Cameron: "the skills needs a way to upload a MD file and read and understand it and apply it very well".

## What was built

- **Upload.** Upload Markdown on the Skills page, or files dropped on it: up to 20 .md, .markdown or .txt files at once, including Claude-style SKILL.md files, whose header's name (or title) and description become the title and when it applies. A leading block is read as a header only when it is one. Every file is shown before it is saved: title, when it applies, length, a rendered preview. A file over 40,000 characters is split at its headings (or paragraph breaks), each part named after the sections it holds. A file that is not UTF-8 is read as Windows text and said so. While files are being added nothing in the review can change; a file or part that fails stays with its reason, and a retry sends only what is left.
- **Understand.** Read and add, or Have Reactor read it on a skill, is an AI run (the button says how many) in which Reactor reads the skill closely, with the other skills' text beside it, and writes down when it applies, what it will do (rules that stand on their own, since they are used in place of a long skill's text), where it would use it, and what is unclear, beyond what it can do, or in conflict. It is kept against the exact text read: any edit, even one made while it is being read, shows it as out of date, and it stops steering the choice until read again. Example questions open Chat with the skill applied, never over a question being typed.
- **Apply.** Skills are chosen by title, when it applies, headings, and the reading's examples, with plurals folded, words most skills use ignored, and a long skill judged by its best section. Each goes to the model in a tagged block (its text cannot close or forge one; nor can a title). A skill too long to show in full goes in brief: what it asks, its headings, and the parts that fit the question; in chat Reactor can read any section (read_skill takes a heading). Email drafts use a skill's own templates and get the best-fitting skill in full up to 12,000 characters. A short skill such as a brand voice can be applied to every answer and draft (up to 4,000 characters each, 8,000 in all). Answers still say which skills they followed, a section cited counting as its skill.
- **Seeing it.** Skills render as documents (headings, lists, tables, emphasis, links, the line breaks typed), and download as .md.

## How it was checked

- Three reviewers looked through different lenses: the server, parsing and prompts; the page in the rig with a battery of real files at 1728, 1280 and 390 wide; and whether skills are applied well, across a 17-skill library and 42 realistic chat questions, report topics and email drafts. They found 39 things (the server suite also failed on one misplaced helper).
- All were worked on; a fourth reviewer re-measured them with the reviewers' own probes: 35 fixed, 4 partly, and 10 new faults from the fixes (2 medium). All 14 were closed and measured again.
- The application table, first wanted skill ranked first: 21 of 42 before, 27 now; with readings 32 before, 37 now. With a brand voice marked for every answer it is in all 25 chat prompts, 7 reports and 10 drafts.
- Tests: 393 page tests, 18 forecast tests and 857 server tests pass. No real AI call was made: the reading's quality and how well a model follows a brief or a template are judged from the prompts.

## The findings

### Server and prompts

| ID | Severity | Finding | Outcome |
|---|---|---|---|
| S-S1 | high | The full server suite fails: _skills_answer is defined inside add_routes but uses nothing from it | Fixed. |
| S-S2 | medium | A skill whose text starts with a '---' rule loses its first block without warning, even after the preview showed it | Fixed. |
| S-S3 | medium | A reading of the old text is marked current when the skill is edited while Reactor is reading it | Fixed. |
| S-S4 | medium | The AI's first 'when it applies' becomes permanent and is later sent back to the model as the merchant's own words | Fixed. |
| S-S5 | medium | Email drafts regressed: a playbook over 8,000 characters no longer reaches the draft, only its opening or a few rules | Fixed. |
| S-S6 | medium | Chat can never read the end of a skill between 30,000 and 40,000 characters that has no headings | Fixed. |
| S-S7 | low | Skills that are picked or named have no total limit, so reports can carry about 117,000 characters of skills | Fixed. |
| S-S8 | low | A cut-off or badly shaped reading is saved as if it were complete | Fixed. |
| S-S9 | low | The reading prompt asks Reactor to spot conflicts it cannot see, and asks for 'short' rules that later stand in for the whole skill | Fixed. |
| S-S10 | low | In chat, a short skill that is just out of room shows the model less than the overflow list would | Fixed. |
| S-S11 | low | The </skill> neutralising is exact-case only, and an opening <skill> tag passes through | Fixed. |
| S-S12 | low | _skill_sections loses headings after a ~~~ fence that contains ```; setext headings and ambiguous partial matches are not handled | Fixed. |
| S-S13 | low | Raw <skill ...> markup now shows in 'What Reactor read' | Partly fixed at the check, then fixed. |
| S-S14 | low | The server and page parsers disagree on names, quotes and multi-line descriptions | Fixed. |
| S-S15 | low | Six of 18 mutations of the new server code are caught by no test | Partly fixed at the check, then fixed. |

### Applying skills

| ID | Severity | Finding | Outcome |
|---|---|---|---|
| A-F1 | high | A long uploaded playbook never reaches drafts or reports in the part that is needed: they get its opening, or the reading's 15 rules, and cannot open a section | Fixed. |
| A-F2 | medium | The draft ranks skills against the fenced transcript, so the words 'customer', the sender's name, the date and the fence token are added to every email | Fixed. |
| A-F3 | medium | Word matching has no plural handling and no weighting for words every skill uses, so the wrong skill often ranks first and the 36k playbook outranks specific skills | Fixed. |
| A-F4 | medium | A brand voice skill is never used in email drafts, and in chat it survives only if it happens to share a word with the question | Fixed. |
| A-F5 | medium | The draft is told never to quote the playbooks, which works against skills that exist to give reply templates, and the reading does not warn what drafts will not do | Fixed. |
| A-F6 | medium | The reading cannot find a conflict with another skill because it sees only their titles, and chat has no rule for which of two conflicting skills wins | Fixed. |
| A-F7 | low | '</SKILL>' in any case, and a forged '<skill title=...>' inside a skill's text, pass into the prompt, and read_skill escapes nothing | Fixed. |
| A-F8 | low | A long skill followed by section is dropped from 'skills followed', and any title is counted whether or not it was shown | Fixed. |
| A-F9 | low | A skill without a 'when' that starts with a heading is listed only by that heading | Fixed. |
| A-F10 | low | Skills for a product plan are ranked on 'product plan <id>', before the product is known | Fixed. |

### The page

| ID | Severity | Finding | Outcome |
|---|---|---|---|
| P-F1 | high | Files added with More files during a run are dropped without a word, and the review's controls look live but do nothing | Fixed. |
| P-F2 | medium | When a middle part fails, the file leaves the review and that section is silently missing | Fixed. |
| P-F3 | medium | A file the server refused becomes a dead end: its fields are gone, the buttons are off, and the panel blocks Upload and New skill | Fixed. |
| P-F4 | medium | Text between two '---' lines at the start of a skill is deleted on save without any notice | Fixed. |
| P-F5 | medium | Opening Preview on a file with a table pushes the review row off the card; the Leave out X and the fields are clipped | Fixed. |
| P-F6 | medium | A file that is not UTF-8 is saved with replacement characters, so prices are lost | Partly fixed at the check, then fixed. |
| P-F7 | medium | The Read and add button counts files, not the AI runs it will start | Fixed. |
| P-F8 | low | Not the same skill back for titles with double quotes or a single hyphenated word, and it slips past the duplicate check | Fixed. |
| P-F9 | low | A description continued on the next line is cut short, and long values are cut mid-word without notice | Fixed. |
| P-F10 | low | Files beyond 20 are dropped silently, and a drop onto the card while reviewing is refused although More files would add them | Fixed. |
| P-F11 | low | Cancel discards the whole review without asking, and focus is lost after Cancel and Leave out | Fixed. |
| P-F12 | low | An example question overwrites a question already half typed in the chat box | Fixed. |
| P-F13 | low | Several common Markdown forms display wrongly (display only: the model still reads the source) | Fixed. |
| P-F14 | low | Messages repeat themselves, contain a double full stop, or describe a split that did not happen | Partly fixed at the check, then fixed. |

### Found by the checking reviewer, all fixed

| # | Severity | Fault |
|---|---|---|
| 1 | medium | Retitling a file after a partial save added its saved parts again, and the button's count went stale. |
| 2 | medium | A skill marked for every answer took the draft's larger slot, so the best-fitting playbook went in brief. |
| 3 | low | No limit on how many skills could be marked for every answer. |
| 4 | low | Skill titles were placed raw outside their tag. |
| 5 | low | The editor's split confirm said 'split at its headings' for text with none. |
| 6 | low | When nothing fitted, chat was not told any skill existed. |
| 7 | low | Choosing skills was three times slower on a large store. |
| 8 | low | Saving a skill for every answer put focus on another skill, and its heading ran into its chip. |
| 9 | low | A changed skill's out-of-date reading still steered which skill was chosen. |
| 10 | low | Focus after picking several files landed on the last. |
