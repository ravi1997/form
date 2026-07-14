
---
version: alpha
name: "A.D.I.Y.O.G.I UI System"
description: "A.D.I.Y.O.G.I uses a calm monochrome-first interface system for structured intelligence workflows. The visual language pairs a serif display face for emphasis with a clean sans-serif body face for clarity. The palette stays near-black, off-white, and graduated grey with no vivid accent colors in the primary UI. Rounded controls, layered card depth, and generous whitespace define the spatial rhythm. This document defines builder UI tokens and presentation rules only; it does not define product naming, product scope, or rendered-content styling."
colors:
  pure-white: "#ffffff"
  surface-subtle: "#edeef1"
  surface-white: "#f7f7f8"
  charcoal: "#1b1b21"
  grey-body: "#61646b"
  grey-muted: "#94979e"
  ink-black: "#121218"
  slate-mid: "#44454c"
  border-light: "#c9cdd2"
typography:
  display-heading:
    fontFamily: "Lora"
    fontSize: "56px"
    fontWeight: "600"
    lineHeight: "64px"
    letterSpacing: "-1.12px"
  section-heading:
    fontFamily: "Lora"
    fontSize: "36px"
    fontWeight: "600"
    lineHeight: "48px"
    letterSpacing: "-0.72px"
  card-heading:
    fontFamily: "Lora"
    fontSize: "32px"
    fontWeight: "600"
    lineHeight: "48px"
  body-large:
    fontFamily: "Instrument Sans"
    fontSize: "16px"
    fontWeight: "400"
    lineHeight: "24px"
    letterSpacing: "-0.32px"
  body-medium:
    fontFamily: "Instrument Sans"
    fontSize: "14px"
    fontWeight: "400"
    lineHeight: "20px"
    letterSpacing: "-0.14px"
  label-medium:
    fontFamily: "Instrument Sans"
    fontSize: "14px"
    fontWeight: "500"
    lineHeight: "20px"
    letterSpacing: "-0.14px"
  label-large:
    fontFamily: "Instrument Sans"
    fontSize: "20px"
    fontWeight: "500"
    lineHeight: "30px"
    letterSpacing: "-0.8px"
  label-small:
    fontFamily: "Instrument Sans"
    fontSize: "18px"
    fontWeight: "500"
    lineHeight: "28px"
    letterSpacing: "-0.36px"
  ui-micro:
    fontFamily: "Inter"
    fontSize: "13px"
    fontWeight: "500"
    lineHeight: "15.6px"
rounded:
  radius-sm: "6px"
  radius-md: "8px"
  radius-lg: "12px"
  radius-xl: "16px"
  radius-2xl: "24px"
  radius-3xl: "32px"
  radius-pill: "999px"
spacing:
  space-2: "2px"
  space-4: "4px"
  space-6: "6px"
  space-8: "8px"
  space-10: "10px"
  space-12: "12px"
  space-14: "14px"
  space-16: "16px"
  space-20: "20px"
  space-24: "24px"
  space-32: "32px"
  space-40: "40px"
  space-48: "48px"
  space-64: "64px"
  space-88: "88px"
  space-96: "96px"
---
## Overview

A.D.I.Y.O.G.I is a structured intelligence system. The UI should support the flow from input capture to transformation to insight. The visual language is monochrome, restrained, and compositional. It should emphasize hierarchy, clarity, and operational calm.

Product naming and product scope are defined in `brand.md` and `vision.md` respectively.
This document is limited to the builder shell, outer application surfaces, and shared UI components that are not part of rendered content.

The interface is not decorative. It should make the lifecycle of data legible.

**Signature traits:**

- Dual typeface system: Lora for emphasis, Instrument Sans for functional UI text.
- Soft, rounded geometry: Controls and surfaces use consistent radius tokens.
- Layered elevation: Depth comes from a small set of validated shadow tokens.

## Colors

The palette uses 9 validated color tokens across 1 theme profile. Semantic roles stay attached to observed usage so generation agents can choose accents without inventing new color meaning.

**Semantic naming:**

- **content-text** maps to `ink-black`: Primary text color for headings, body copy, and key labels.
- **surface-background** maps to `surface-white`: Base page background and large container fill.
- **action-background** maps to `pure-white`: Card surfaces, button fills, and inset highlight layers.
- **action-text** maps to `charcoal`: Primary action text and dark surface text.

### Text Scale

- **Charcoal** (#1b1b21): Primary action text and dark card backgrounds. Role: text. {authored: rgb(27, 27, 33), space: rgb}
- **Grey Body** (#61646b): Body copy, navigation text, and descriptive paragraphs. Role: text. {authored: rgb(97, 100, 107), space: rgb}
- **Grey Muted** (#94979e): Muted captions, stat labels, and secondary descriptors. Role: text. {authored: rgb(148, 151, 158), space: rgb}
- **Ink Black** (#121218): Primary heading and body text color; used on headings and key UI labels. Role: text. {authored: rgb(18, 18, 24), space: rgb}
- **Slate Mid** (#44454c): Secondary text, subheadings, and muted UI labels. Role: text. {authored: rgb(68, 69, 76), space: rgb}

### Interactive

- **Border Light** (#c9cdd2): Dividers, card borders, and shadow color layers. Role: border. {authored: rgb(201, 205, 210), space: rgb}

### Surface & Shadows

- **Pure White** (#ffffff): Card surfaces, button fills, and inset highlight layers. Role: background. {authored: rgb(255, 255, 255), space: rgb, alpha: 0}
- **Surface Subtle** (#edeef1): Ghost button background and subtle section fills. Role: background. {authored: rgb(237, 238, 241), space: rgb, alpha: 0}
- **Surface White** (#f7f7f8): Page background and large container fill. Role: background. {authored: rgb(247, 247, 248), space: rgb}

## Typography

Typography uses Lora, Instrument Sans, and Inter across the hierarchy. Keep the mapping stable before adding any decorative type styles.

The display system uses Lora for structure and emphasis. The body system uses Instrument Sans for readability.

### Font Roles

- **Headline Font**: Lora
- **Body Font**: Instrument Sans

### Type Scale Evidence

| Role                                           | Font            | Size | Weight | Line Height | Letter Spacing | Stack / Features                                                                                           | Notes           |
| ---------------------------------------------- | --------------- | ---- | ------ | ----------- | -------------- | ---------------------------------------------------------------------------------------------------------- | --------------- |
| Hero headline                                  | Lora            | 56px | 600    | 64px        | -1.12px        | Lora, Lora Placeholder, serif; features: "blwf", "cv03", "cv04", "cv09", "cv11"                            | Extracted token |
| Section headings                               | Lora            | 36px | 600    | 48px        | -0.72px        | Lora, Lora Placeholder, serif; features: "blwf", "cv03", "cv04", "cv09", "cv11"                            | Extracted token |
| Card and callout headings                      | Lora            | 32px | 600    | 48px        | normal         | Lora, Lora Placeholder, serif; features: "blwf", "cv03", "cv04", "cv09", "cv11"                            | Extracted token |
| Primary body copy                              | Instrument Sans | 16px | 400    | 24px        | -0.32px        | Instrument Sans, Instrument Sans Placeholder, sans-serif; features: "blwf", "cv03", "cv04", "cv09", "cv11" | Extracted token |
| Secondary body text                            | Instrument Sans | 14px | 400    | 20px        | -0.14px        | Instrument Sans, Instrument Sans Placeholder, sans-serif; features: "blwf", "cv03", "cv04", "cv09", "cv11" | Extracted token |
| Navigation links, button labels, and UI labels | Instrument Sans | 14px | 500    | 20px        | -0.14px        | Instrument Sans, Instrument Sans Placeholder, sans-serif; features: "blwf", "cv03", "cv04", "cv09", "cv11" | Extracted token |
| Stat numbers and prominent callout labels      | Instrument Sans | 20px | 500    | 30px        | -0.8px         | Instrument Sans, Instrument Sans Placeholder, sans-serif; features: "blwf", "cv03", "cv04", "cv09", "cv11" | Extracted token |
| Sub-section labels and card titles             | Instrument Sans | 18px | 500    | 28px        | -0.36px        | Instrument Sans, Instrument Sans Placeholder, sans-serif; features: "blwf", "cv03", "cv04", "cv09", "cv11" | Extracted token |
| Badge labels and micro UI text                 | Inter           | 13px | 500    | 15.6px      | normal         | Inter, Inter Placeholder, sans-serif                                                                       | Extracted token |

## Layout

Responsive system uses 2 breakpoint tier(s): mobile, tablet.

This system uses an 8px base grid with scale values 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 32, 40, 48, 64, 88, 96.

### Responsive Strategy

- **mobile (<= 809.98px)**: Constrain layout for small viewports and prioritize vertical stacking.
- **tablet (810-1199.98px)**: Increase spacing and column structure for medium-width viewports.

### Spacing System

| Token    | Value | Px | Notes                   |
| -------- | ----- | -- | ----------------------- |
| space-2  | 2px   | 2  | Extracted spacing token |
| space-4  | 4px   | 4  | Extracted spacing token |
| space-6  | 6px   | 6  | Extracted spacing token |
| space-8  | 8px   | 8  | Extracted spacing token |
| space-10 | 10px  | 10 | Extracted spacing token |
| space-12 | 12px  | 12 | Extracted spacing token |
| space-14 | 14px  | 14 | Extracted spacing token |
| space-16 | 16px  | 16 | Extracted spacing token |
| space-20 | 20px  | 20 | Extracted spacing token |
| space-24 | 24px  | 24 | Extracted spacing token |
| space-32 | 32px  | 32 | Extracted spacing token |
| space-40 | 40px  | 40 | Extracted spacing token |
| space-48 | 48px  | 48 | Extracted spacing token |
| space-64 | 64px  | 64 | Extracted spacing token |
| space-88 | 88px  | 88 | Extracted spacing token |
| space-96 | 96px  | 96 | Extracted spacing token |

## Elevation & Depth

Keep depth flat unless validated shadow or interaction evidence appears in the extraction payload. Do not invent shadows beyond this evidence boundary.

### Shadow Evidence

| Shadow Token      | Layers | Details                               |
| ----------------- | ------ | ------------------------------------- |
| card-elevated     | 4      | 0px 4px 8px -4px rgb(201, 205, 210)   |
| button-dark       | 3      | inset 0px 2px 0px 0px rgb(68, 69, 76) |
| card-flat         | 2      | 0px 4px 8px -4px rgb(201, 205, 210)   |
| button-dark-hover | 3      | 0px 4px 8px -4px rgb(148, 151, 158)   |

### Interaction Signals

| Theme | Signal          | Evidence                                                                                                                    |
| ----- | --------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Light | backdrop-filter | blur(8px)                                                                                                                   |
| Light | outline-color   | rgb(0, 0, 0) ; rgb(18, 18, 24) ; rgb(0, 0, 238)                                                                             |
| Light | outline-width   | 3px                                                                                                                         |
| Light | outline-offset  | 0px                                                                                                                         |
| Light | transform       | matrix(1, 0, 0, 1, 0, 64) ; matrix3d(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, -0.000833333, 0, 96, 0, 1) ; matrix(1, 0, 0, 1, 3, 3) |

## Shapes

Shape language maps directly to rounded tokens. Keep component corners consistent with the role mapping below before introducing bespoke geometry.

### Radius Roles

| Token       | Value | Px  | Role Mapping         |
| ----------- | ----- | --- | -------------------- |
| radius-sm   | 6px   | 6   | Subtle corner        |
| radius-md   | 8px   | 8   | Control corner       |
| radius-lg   | 12px  | 12  | Control corner       |
| radius-xl   | 16px  | 16  | Card corner          |
| radius-2xl  | 24px  | 24  | Large surface corner |
| radius-3xl  | 32px  | 32  | Large surface corner |
| radius-pill | 999px | 999 | Large surface corner |

### Geometry Evidence

| Radius Token | Shape | Units |
| ------------ | ----- | ----- |
| radius-sm    | 6px   | px    |
| radius-md    | 8px   | px    |
| radius-lg    | 12px  | px    |
| radius-xl    | 16px  | px    |
| radius-2xl   | 24px  | px    |
| radius-3xl   | 32px  | px    |
| radius-pill  | 999px | px    |

## Components

(none detected)

## Do's and Don'ts

Guardrails protect the monochrome palette, dual typeface system, and layered elevation without adding unsupported visual claims.

| Do                                                                            | Don't                                                      |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Do maintain consistent spacing using the base grid                            | Don't make unsupported claims about absent visual features |
| Do maintain WCAG AA contrast ratios (4.5:1 for normal text)                   | Don't mix rounded and sharp corners in the same view       |
| Do use the primary color only for the single most important action per screen |                                                            |
| Do verify evidence before writing new design-system guidance                  |                                                            |

## Responsive Evidence

### Breakpoints

| Name         | Width         | Key Changes                                   |
| ------------ | ------------- | --------------------------------------------- |
| Breakpoint 1 | <= 809.98px   | (max-width: 809.98px)                         |
| Tablet       | 810-1199.98px | (min-width: 810px) and (max-width: 1199.98px) |

## Agent Prompt Guide

### Example Component Prompts

- Create a button component using the validated primary color role and spacing tokens.
- Create a card component using mapped radius role and evidence-backed elevation.
- Create a form input component using inferred typography hierarchy and border roles.

### Iteration Guide

1. Start with extracted palette and typography roles only.
