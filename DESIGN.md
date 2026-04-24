# Design System Inspired by Stripe

## 1. Visual Theme & Atmosphere

Stripe's website is the gold standard of fintech design -- a system that manages to feel simultaneously technical and luxurious, precise and warm. The page opens on a clean white canvas ("#ffffff") with deep navy headings ("#061b31") and a signature purple ("#7c83f7") that permeates the entire system. The effect is unmistakably Stripe: elegant gradients, generous whitespace, and a sense of premium infrastructure.

## 2. Color Palette

### Brand Colors
- **Purple Primary**: `#7c83f7`
- **Purple Dark**: `#5b63d6`
- **Purple Light**: `#a5aafb`
- **Deep Navy**: `#061b31`

### Neutral Scale
- **Slate 900**: `#0f172a`
- **Slate 800**: `#1e293b`
- **Slate 700**: `#334155`
- **Slate 600**: `#475569`
- **Slate 500**: `#64748b`
- **Slate 400**: `#94a3b8`
- **Slate 300**: `#cbd5e1`
- **Slate 200**: `#e2e8f0`
- **Slate 100**: `#f1f5f9`
- **Slate 50**: `#f8fafc`

### Semantic Colors
- **Success**: `#10b981` (Emerald 500)
- **Warning**: `#f59e0b` (Amber 500)
- **Error**: `#ef4444` (Red 500)
- **Info**: `#3b82f6` (Blue 500)

## 3. Typography

### Font Stack
- **Primary**: "Söhne" (Stripe's custom typeface), fallback to "Inter", system-ui, sans-serif
- **Monospace**: "SourceCodePro", "Fira Code", monospace

### Type Scale
- **Display**: 64px / 1.1 line-height / -0.02em tracking / 300 weight
- **H1**: 48px / 1.2 / -0.02em / 300
- **H2**: 36px / 1.25 / -0.01em / 300
- **H3**: 24px / 1.3 / -0.01em / 400
- **Body Large**: 20px / 1.5 / 0em / 300
- **Body**: 16px / 1.5 / 0em / 300
- **Small**: 14px / 1.5 / 0em / 400
- **Caption**: 12px / 1.4 / 0.01em / 400

### Important Typographic Rules
- Weight 300 is the default; use 400 only for buttons/links/navigation
- Always enable `font-feature-settings: "ss01"` on custom typeface text
- Use `"tnum"` for any numbers in tables, charts, or financial displays

## 4. Buttons

### Primary Button
```css
background: linear-gradient(84.88deg, #7c83f7 0%, #a5aafb 100%);
color: #ffffff;
padding: 12px 24px;
border-radius: 6px;
font-size: 16px;
font-weight: 400;
transition: all 0.15s ease;
```

### Secondary Button
```css
background: transparent;
color: #061b31;
border: 1px solid #e2e8f0;
padding: 12px 24px;
border-radius: 6px;
font-size: 16px;
font-weight: 400;
```

### Ghost Button
```css
background: transparent;
color: #7c83f7;
padding: 12px 24px;
border-radius: 6px;
font-size: 16px;
font-weight: 400;
```

### Button States
- Hover: subtle lift with enhanced shadow
- Active: slight scale down (0.98)
- Disabled: 50% opacity, no pointer events
- Loading: spinner icon, maintain width

## 5. Cards

### Standard Card
```css
background: #ffffff;
border: 1px solid #e2e8f0;
border-radius: 8px;
padding: 32px;
box-shadow: rgba(50,50,93,0.25) 0px 2px 4px -1px, rgba(0,0,0,0.08) 0px 4px 6px -1px;
```

### Premium Card (with gradient border)
```css
background: linear-gradient(#ffffff, #ffffff) padding-box,
            linear-gradient(135deg, #7c83f7, #a5aafb) border-box;
border: 1px solid transparent;
border-radius: 8px;
```

### Interactive Card
```css
transition: all 0.2s ease;
cursor: pointer;
```
Hover: lift with increased shadow, subtle purple border glow

## 6. Forms

### Input Field
```css
background: #ffffff;
border: 1px solid #e2e8f0;
border-radius: 6px;
padding: 12px 16px;
font-size: 16px;
font-weight: 300;
color: #061b31;
transition: all 0.15s ease;
```

### Input States
- Default: 1px solid #e2e8f0
- Focus: 2px solid #7c83f7, ring shadow
- Error: 1px solid #ef4444, red text
- Disabled: background #f8fafc, 50% opacity

### Label
```css
font-size: 14px;
font-weight: 400;
color: #475569;
margin-bottom: 8px;
display: block;
```

## 7. Spacing System

Base unit: 4px

- **0**: 0px
- **1**: 4px
- **2**: 8px
- **3**: 12px
- **4**: 16px
- **5**: 20px
- **6**: 24px
- **8**: 32px
- **10**: 40px
- **12**: 48px
- **16**: 64px
- **20**: 80px
- **24**: 96px

## 8. Border Radius

- **0**: 0px
- **1**: 4px
- **2**: 6px
- **3**: 8px
- **4**: 12px
- **pill**: 9999px

## 9. Elevation / Shadows

### Subtle
```css
box-shadow: rgba(50,50,93,0.08) 0px 1px 2px 0px
```

### Card
```css
box-shadow: rgba(50,50,93,0.25) 0px 2px 4px -1px, rgba(0,0,0,0.08) 0px 4px 6px -1px
```

### Modal
```css
box-shadow: rgba(50,50,93,0.5) 0px 10px 25px -5px, rgba(0,0,0,0.15) 0px 8px 10px -6px
```

### Formula: `rgba(50,50,93,0.25) 0px Y1 B1 -S1, rgba(0,0,0,0.1) 0px Y2 B2 -S2`

## 10. Dark Mode

### Dark Surface Colors
- **Dark Background**: `#1c1e54` (deep branded indigo, NOT black)
- **Dark Card**: `#252747`
- **Dark Border**: `#3d3f6e`
- **Dark Text Primary**: `#ffffff`
- **Dark Text Secondary**: `#94a3b8`
- **Dark Accent**: `#7c83f7`
- **Dark Accent Hover**: `#9499f8`

### Dark Mode Rules
- Use `#1c1e54` as dark background -- not black, not gray
- Reduce gradient opacity by 10-15% in dark mode
- Maintain purple accent in dark mode for brand consistency

## Iteration Guide

1. Always enable `font-feature-settings: "ss01"` on sohne-var text -- this is the brand's typographic DNA
2. Weight 300 is the default; use 400 only for buttons/links/navigation
3. Shadow formula: `rgba(50,50,93,0.25) 0px Y1 B1 -S1, rgba(0,0,0,0.1) 0px Y2 B2 -S2` where Y1/B1 are larger (far shadow) and Y2/B2 are smaller (near shadow)
4. Heading color is `#061b31` (deep navy), body is `#64748d` (slate), labels are `#273951` (dark slate)
5. Border-radius stays in the 4px-8px range -- never use pill shapes or large rounding
6. Use `"tnum"` for any numbers in tables, charts, or financial displays
7. Dark sections use `#1c1e54` -- not black, not gray, but a deep branded indigo
8. SourceCodePro for code at 12px/500 with 2.00 line-height (very generous for readability)
