# Workspace pages review, 24 September 2026

Cameron: "we need to improve some of what im calling the legacy pages". Asked which, he chose the Workspace pages (Memory, Skills, Chat and the Guide) and "comprehensive improvements wherever they can be made". Of the proposals put to him he chose one, in his words "i want the app to be better at using and reading skills and applying them", and two layout calls: move the sidebar's "Have something in mind?" card, and show Refresh all on the report pages only. Customise stays on Memory and Skills.

## How it was checked

- Three reviewers took the four pages and the sidebar shell on a seeded local copy of the app at 1728, 1280, 1024 and 390 wide, as master, admin, member and part-timer, and returned 98 findings: 74 faults, 12 improvements and 12 proposals.
- Everything that was not a proposal was worked on, with the skills work Cameron chose. A fourth reviewer then re-measured all 86: 77 fixed, 8 partly, 1 not fixed, and 16 new faults the changes had made (4 medium, 12 low). All 25 were closed and measured again with that reviewer's own probes.
- Tests: 387 page tests, 18 forecast tests and 847 server tests pass, and the new server tests fail on the code before this change.

## What Reactor now does with skills

- It picks the skills that fit each question (by title, then by the words they share with it), in chat, in the four AI reports and in email reply drafts. Before, every skill went in newest first until 24,000 characters were spent, so the oldest were cut to a title whatever was asked.
- It can open any other skill by title with a tool of its own, which reads the skill and never touches the store.
- Every answer and report says which skills it followed ("Followed your skill Discounting policy", a link to Skills), and each skill says how many answers have followed it and when last.
- Use in chat on a skill, or the Skills button beside the question box, applies a skill to a conversation whatever the question.
- A rule someone asks Memory to keep, which Memory refuses because it reads as an instruction, is offered as a new skill, but only when it is the person's own words: an instruction lifted from an order note or an email the answer read is never offered.
- A skill holds 12,000 characters, and a longer file can be split into several.

## Decided with Cameron, or left

- Conversations stay in the browser (keeping them on the server, CH-P1, was not chosen). They now survive a sign-out or an expired sign-in on the same computer, and are cleared when someone else signs in there.
- Chat closes a follow-up only when the person's own words name it; one the answer merely thinks is done is offered with Mark done.
- The daily AI budget message gives no figure: the cap is kept in dollars, and a pound figure would be a guess.
- Not built, as proposals not chosen: house notes in the Guide, votes on requests, a per-page link into the Guide, the author of each note and skill, and Remembered with Undo in chat.
- The Size list overflows by 21px on a phone, as it did before this change; it is outside these pages.

## The release notes

What's new had stopped at 8 Sep. Notes are now written for 8 to 24 Sep, and the older ones no longer carry dashes, the code name or developer words. A page test now fails if the newest note is older than the last change to copilot.py or static/index.html, so the notes cannot fall behind the app again.

## The findings

### Chat

| ID | Kind | Area | Finding | Outcome |
|---|---|---|---|---|
| CH-01 | high | Chat | Signing out, or a session expiring, deletes every conversation | Fixed. |
| CH-02 | high | Chat | Follow-up questions lose most of what the last answer said | Fixed. |
| CH-03 | high | Chat | When storage fills, new answers are lost without a word | Fixed. |
| CH-04 | medium | Chat | A failed or cut-off answer strands the question, and asking again sends it twice | Fixed. |
| CH-05 | medium | Chat | Two open tabs overwrite each other's conversations | Fixed. |
| CH-06 | medium | Chat | An answer still running is lost from view, and when it lands it disturbs the conversation being read | Fixed. |
| CH-07 | medium | Chat | While an answer runs, Enter, starters and follow-ups do nothing and say nothing | Fixed. |
| CH-08 | medium | Chat | Email addresses and long codes push the chat sideways on a phone | Fixed. |
| CH-09 | medium | Chat | The Chat heading changes with the route taken and goes out of date | Fixed. |
| CH-10 | medium | Chat | A new answer arrives scrolled to its end, with its headline off screen | Fixed. |
| CH-11 | medium | Chat | Track and Mark done are forgotten, so the same action can be tracked twice | Fixed. |
| CH-12 | medium | Chat | Selecting an action's text to copy it ticks it done | Fixed. |
| CH-13 | medium | Chat | Server wording in chat breaks the house rules: setting names, Railway, US spelling, tool names | Fixed after the check: the budget message no longer quotes a figure. |
| CH-14 | medium | Chat | 'Show the data behind this' shows raw JSON cut off mid-value | Fixed. |
| CH-15 | medium | Chat | An answer given as prose shows as one run-on block with literal markdown | Fixed after the check: an empty answer has Ask again, and the page chat no longer says "(no response)". |
| CH-16 | medium | Chat | Every refusal from the streaming route is sent a second time | Fixed. |
| CH-17 | medium | Chat | Every answer triggers a Shopify, Analytics and Search Console read for a page that is not open | Fixed. |
| CH-18 | low | Chat | An account without the Chat tab still gets Conversations and New chat | Fixed. |
| CH-19 | low | Chat | New chat stacks up empty conversations | Fixed. |
| CH-20 | low | Chat | The whole conversation fades in again on every question | Fixed. |
| CH-21 | low | Chat | A fall in refunds is painted red | Fixed. |
| CH-22 | low | Chat | Screen readers are not told about the answer, and focus is dropped | Fixed. |
| CH-23 | low | Chat | Conversation titles are cut mid-word and cannot be seen in full or changed | Fixed. |
| CH-24 | low | Chat | Metric tiles in an answer are sized by the screen, not by the chat column | Fixed. |
| CH-I1 | improvement | Chat | The conversation list does not help anyone find a past answer | Fixed. |
| CH-I2 | improvement | Chat | Answers carry no date, so old figures read as current | Fixed. |
| CH-I3 | improvement | Chat | No way to copy or keep an answer | Fixed after the check: each action can be copied, and Download as PDF prints the open conversation. |
| CH-I4 | improvement | Chat | A long run has no Stop and no sense of time | Fixed. |
| CH-I5 | improvement | Chat | Deep analysis stays on across conversations and is never explained | Fixed. |
| CH-I6 | improvement | Chat | Sections are closed by default, hiding what the answer actually found | Fixed. |
| CH-I7 | improvement | Chat | After a reload, and on a phone, earlier conversations are out of sight | Fixed. |
| CH-I8 | improvement | Chat | Long conversations hit a dead end | Fixed. |
| CH-I9 | improvement | Chat | Small composer and copy details | Fixed. |
| CH-P1 | proposal | Chat | Keep conversations on the server, per person, with the option to share | Not built (a proposal, not chosen). |
| CH-P2 | proposal | Chat | Starters and saved questions that fit this business and this person | Not built (a proposal, not chosen). |
| CH-P3 | proposal | Chat | Ask Reactor from the search box on any page | Not built (a proposal, not chosen). |
| CH-P4 | proposal | Chat | Link answers to the app's own pages | Not built (a proposal, not chosen). |

### Memory and Skills

| ID | Kind | Area | Finding | Outcome |
|---|---|---|---|---|
| MS-01 | high | Skills | Half-typed skills are thrown away by any other action on the page | Fixed. |
| MS-02 | high | Memory and Skills | Delete is one tap on a 24px icon beside Edit or Done, with no confirm and no undo | Fixed after the check: on a touch screen the note and skill buttons are 32px with room between. |
| MS-03 | high | Skills | Load from file and paste cut a skill to 6,000 characters without saying so, and replace what was typed | Fixed. |
| MS-04 | medium | Memory | The page promises 'Edit or remove anything here' but notes cannot be edited or added | Fixed. |
| MS-05 | medium | Memory | Ordinary notes the owner asks Reactor to remember are silently refused | Fixed. |
| MS-06 | medium | Memory | A busy AI window makes Store knowledge look unlearned and invites a paid re-learn | Fixed. |
| MS-07 | medium | Memory | Memory is blank until a Shopify orders read finishes, and that read runs after every chat answer | Fixed. |
| MS-08 | medium | Memory | Tracked impact figures keep moving after 'Concluded', and the learning it writes breaks the house number and date style | Fixed. |
| MS-09 | medium | Memory | Follow-ups can only be closed by hand, and dismissed ones look open | Fixed. |
| MS-10 | medium | Memory and Skills | The Customise hide button covers Store knowledge's Delete and the first card of every group | Fixed. |
| MS-11 | medium | Memory and Skills | An unreadable store shows as empty, and writes to it look saved but are lost | Fixed. |
| MS-12 | medium | Skills | Editing a skill happens in a 104px box with no count, and focus is dropped | Fixed after the check: focus lands on the skill just saved, or the next one after a delete. |
| MS-13 | medium | Skills | After a failed read, the page says not to add a skill but leaves the form live | Fixed after the check: "could not be loaded, so they cannot be shown yet". |
| MS-14 | medium | Memory and Skills | Error copy shows server internals, US spelling and a spaced hyphen | Fixed. |
| MS-15 | medium | Memory and Skills | Screen readers get no structure and no context on the icon buttons | Fixed. |
| MS-16 | medium | Memory | At phone width, notes are squeezed into a column about 40% of the card | Fixed after the check: stacked notes drop the table's 460px floor, with a date and source line under each note. |
| MS-17 | low | Memory and Skills | Type chips are coloured, and Fact and Preference share a colour | Fixed. |
| MS-18 | low | Skills | Expanding one skill stretches every card in its row to the same height | Fixed. |
| MS-19 | low | Skills | Validation is a toast only, the title limit is silent, and duplicate titles are allowed | Fixed after the check: Enter in the title moves to the text. |
| MS-20 | low | Skills | Leaving Skills removes the warning for an unsaved skill | Fixed. |
| MS-21 | low | Memory and Skills | Each click replays the entrance animation on every card | Fixed. |
| MS-22 | low | Memory | View what was learned prints Markdown marks and scrolls inside a 360px box | Fixed. |
| MS-23 | low | Memory | Learn my store gives no sign it is a paid AI run, and its busy state is a greyed button | Fixed. |
| MS-24 | low | Memory and Skills | Uneven spacing: 24px between a skill's title and body, and doubled gaps between cards | Fixed. |
| MS-25 | improvement | Memory | Memory cannot be searched, filtered, sorted or paged, and shows no dates or source | Fixed. |
| MS-26 | improvement | Memory and Skills | Neither page says which notes and skills Reactor actually receives | Fixed. |
| MS-27 | improvement | Skills | A 350px Add form sits above the list every time | Fixed. |
| MS-28 | improvement | Memory | Stored knowledge cannot be corrected | Fixed. |
| MS-29 | proposal | Memory | Show in chat what Reactor remembered, with Undo | Not built (a proposal, not chosen). |
| MS-30 | proposal | Memory and Skills | Anyone with the tab can rewrite what steers every answer, with no author shown | Not built (a proposal, not chosen). |
| MS-31 | proposal | Skills | Make a skill easy to put to work and see when it is used | Built: it is the skills work Cameron chose. |
| MS-32 | proposal | Memory and Skills | Customise adds little here | Not built (a proposal, not chosen). |

### Guide and the sidebar

| ID | Kind | Area | Finding | Outcome |
|---|---|---|---|---|
| GD-01 | high | Guide / What's new | What's new stops at 8 Sep, so the panel describes a build 16 days older than the one running | Fixed. |
| GD-02 | medium | Guide | Several Guide entries are now wrong about how the app works | Fixed. |
| GD-03 | medium | Guide | Guide copy breaks house rules: setting names, Railway, the code name, a hard-coded host, and developer setup steps | Fixed. |
| GD-04 | medium | Guide / What's new | Release notes contain 46 em dashes, the code name 'gizmo' and developer jargon | Fixed. |
| GD-05 | medium | Guide / Requests | 'Cameron gets an email' is promised even when no email can be sent | Fixed. |
| GD-06 | medium | Guide / Requests | Requests cannot be answered or tidied from the app, and the person who asked is never told | Fixed. |
| GD-07 | medium | Workspace shell (sidebar and phone drawer) | At laptop heights the whole Workspace group, and the Guide's unread dot, is below the fold of a sidebar with no scrollbar | Fixed. |
| GD-08 | medium | Workspace shell (phone drawer, topbar) | Keyboard and screen-reader faults: the drawer cannot be reached with Tab, and the phone search button has no name | Fixed. |
| GD-09 | low | Guide / Requests | A request sent while the Requests tab is open does not appear in the list | Fixed. |
| GD-10 | low | Guide (unread dot) | The unread dot compares dates only and is kept per browser, not per person | Fixed. |
| GD-11 | low | Guide | Tab buttons do not say which is selected, and pressing one throws keyboard focus away | Fixed after the check: focus returns to the row's picker or Reply after a triage write. |
| GD-12 | low | Guide / Requests | A long unbroken word in a request title pushes the card past a phone screen | Fixed. |
| GD-13 | low | Guide / Requests (Ask for a feature window) | The Ask for a feature form gives weak guidance and cuts long text without saying so | Fixed. |
| GD-14 | low | Guide / What's new and Requests | 'Fixed' notes are painted error red and 'Planned' warning amber, which breaks the neutral-chip rule | Fixed. |
| GD-15 | low | Workspace shell (sidebar) | 'Refresh all reports' runs four reports, not all of them, and shows even to accounts that cannot open them | Fixed. |
| GD-20 | improvement | Guide | A new team member cannot learn most of the desk from the Guide: 12 of 19 sidebar pages are not covered | Fixed. |
| GD-21 | improvement | Guide / What's new | What's new is one card 30,755px tall with every note open, most of its width blank, and the headline in the smallest type | Fixed. |
| GD-22 | improvement | Guide / Requests | The Requests list lags behind the house list pattern: no filter tabs, counts, pager, sort or page | Fixed. |
| GD-23 | improvement | Guide / topbar search | The Guide has no contents or search, and the topbar search cannot find help | Fixed. |
| GD-24 | improvement | Guide | The two-column Guide grid leaves blocks of empty space | Fixed. |
| GD-25 | improvement | Guide | Everyone gets the same Guide, admin-only steps included | Fixed. |
| GD-26 | improvement | Guide / What's new and Requests | Every switch to What's new or Requests downloads the full 80KB again, and the dot check downloads it too | Fixed. |
| GD-27 | improvement | Guide | Page structure is weak for screen readers, and the header does not change with the tab | Fixed. |
| GD-28 | improvement | Workspace shell (phone) | On a phone, Ask for a feature is three taps deep and its fields zoom the page | Fixed. |
| GD-29 | improvement | Guide (Print this) | Print this can only print the whole Guide, setup pages included | Fixed. |
| GD-40 | proposal | Guide / every page | Open the Guide from each page and link release notes to pages | Partly: release notes carry an Open link to their page; no per-page Guide link. |
| GD-41 | proposal | Guide / Requests | Make Requests a two-way channel | Not built (a proposal, not chosen). |
| GD-42 | proposal | Guide | Let admins add house notes to the Guide | Not built (a proposal, not chosen). |
| GD-43 | proposal | Workspace shell (sidebar) | Consider moving the permanent support card and demoting Refresh all | Built: Cameron chose both halves. |

## Found by the checking reviewer, all fixed

| # | Severity | Fault | 
|---|---|---|
| 1 | medium | Buttons hidden by the page still showed (.btn's own display beat [hidden]); Split made a duplicate or "Saved as 0 skills". |
| 2 | medium | Notes were cut off on a phone: the stacked rows kept the table's 460px floor. |
| 3 | medium | Opening a long conversation saved every conversation once per open section (1,149ms with a large store). |
| 4 | medium | The Chat empty state scrolled sideways on a phone. |
| 5 | low | Use in chat threw for an account without the Chat tab. |
| 6 | low | Escape in a conversation rename kept the new name. |
| 7 | low | Deleting a skill while another was being written left it listed. |
| 8 | low | A full store deleted whole conversations before trimming the previews of short ones. |
| 9 | low | An applied skill showed as "A skill" after a reload. |
| 10 | low | Chat closed follow-ups on the model's word alone. |
| 11 | low | A correction to store knowledge was cut at 8,000 characters without a word. |
| 12 | low | The skill editor's count was read out after every pause in typing. |
| 13 | low | After Log out, the last person's conversation titles were in the page behind the sign-in card. |
| 14 | low | Ask for a feature from the phone drawer left the drawer over an unusable page. |
| 15 | low | The Skills picker showed what was applied by a tick alone. |
| 16 | low | Two older skills sharing a title could not be edited. |
