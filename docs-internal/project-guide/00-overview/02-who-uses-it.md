# Who Uses It

> **Purpose:** Describe intended users and the decisions the interface must support.
> **Read this before:** Changing dashboard information architecture, copy, or workflow.
> **Source files:** `linkreach/dashboard/templates/dashboard/`, `../../linkedin-profile-ui-plan/01-user-perspective.md`

## Primary user: outreach operator

The operator needs to:

1. connect and verify a LinkedIn account;
2. configure an AI provider and campaign context;
3. import or discover suitable leads;
4. understand each lead's campaign, state, country, and contact availability;
5. start the bot safely and see whether it is actually working;
6. inspect failures, conversations, and outcomes without using the terminal.

The UI should use product language, not implementation language. For example,
show “Verification required” instead of exposing an authentication exception.

## Secondary user: maintainer or contributor

This user needs to understand which module owns a behavior, how state moves, where
external calls happen, which writes trigger side effects, and which tests prove a
change is safe. Section [05-before-you-change](../05-before-you-change/README.md)
is written primarily for this user.

## Current limits

- `LinkedInProfile.user` is one-to-one, but the daemon selects the first active profile.
- `SiteConfig` and `BotProcess` are global singletons.
- most dashboard queries are not filtered by the logged-in user.
- email sending is Layer 1: one outbound message, with no inbound email processing.

