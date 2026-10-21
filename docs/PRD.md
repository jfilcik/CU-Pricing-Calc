# Azure AI Content Understanding Pricing Calculator

Calculate costs for Azure AI Content Understanding services with precision and transparency across different deployment models.

**Experience Qualities**:
1. **Precise** - Provides accurate cost calculations based on actual Azure pricing models
2. **Transparent** - Shows detailed breakdowns of each cost component 
3. **Professional** - Clean, business-focused interface suitable for enterprise planning

**Complexity Level**: Light Application (multiple features with basic state)
- Interactive calculator with multiple input types and real-time calculations across various Azure AI services

## Essential Features

**File Type Selection**
- Functionality: Choose between document, image, video, audio, and text processing
- Purpose: Different file types have different pricing models and processing requirements
- Trigger: User selects file type from dropdown
- Progression: Selection → Auto-updates quantity defaults → Recalculates pricing
- Success criteria: Correct pricing model applied with appropriate units

**Content Extraction Pricing**
- Functionality: Calculates base processing costs for extracting content from files
- Purpose: Core service pricing that applies to most file types (free for text, N/A for images)
- Trigger: Automatic based on file type and quantity
- Progression: File type + quantity → CE calculation → Display cost
- Success criteria: Accurate per-unit pricing with clear cost breakdown

**Field Extraction Configuration**
- Functionality: Advanced AI processing with generative models, embeddings, and contextualization
- Purpose: Optional premium features for enhanced content understanding
- Trigger: User enables/disables field extraction toggle
- Progression: Toggle on → Model selection → Token customization → Cost calculation
- Success criteria: Detailed token-based pricing with model-specific rates

**Deployment Model Selection**
- Functionality: Choose between Global, Regional, Data Zone, or PTU deployment types
- Purpose: Different deployment models have different pricing structures
- Trigger: User selects deployment type
- Progression: Selection → Updates pricing rates → Recalculates all costs
- Success criteria: Correct rate application with PTU handling

**Real-time Cost Calculation**
- Functionality: Live updates of all pricing components as inputs change
- Purpose: Immediate feedback for planning and budgeting decisions
- Trigger: Any input field change
- Progression: Input change → Calculation → Highlighted updates → Display results
- Success criteria: Sub-second updates with visual feedback on changes

## Edge Case Handling

- **Invalid inputs**: Graceful handling of non-numeric or negative values with fallbacks to defaults
- **Missing model data**: Error boundaries prevent crashes when model configurations are incomplete
- **PTU deployments**: Special handling to show token counts instead of costs for PTU pricing models
- **Large numbers**: Proper formatting and display of very small or very large monetary amounts
- **Configuration persistence**: User preferences saved across sessions using persistent storage

## Design Direction

The design should feel professional, trustworthy, and data-focused - emphasizing clarity and precision over visual flair to build confidence in financial calculations.

## Color Selection

Analogous (adjacent colors on color wheel) - Using a blue-based professional palette that conveys trust and reliability in financial calculations.

- **Primary Color**: Professional blue `oklch(0.45 0.15 240)` - Communicates trust and reliability for financial data
- **Secondary Colors**: Light grays `oklch(0.95 0 0)` - Clean backgrounds that don't compete with data
- **Accent Color**: Warm orange `oklch(0.65 0.18 45)` - Draws attention to totals and key calculations
- **Foreground/Background Pairings**: 
  - Background (White `oklch(1 0 0)`): Dark gray text `oklch(0.2 0 0)` - Ratio 10.4:1 ✓
  - Primary (Blue `oklch(0.45 0.15 240)`): White text `oklch(1 0 0)` - Ratio 9.2:1 ✓
  - Secondary (Light Gray `oklch(0.95 0 0)`): Dark gray text `oklch(0.2 0 0)` - Ratio 9.8:1 ✓
  - Accent (Warm Orange `oklch(0.65 0.18 45)`): White text `oklch(1 0 0)` - Ratio 4.8:1 ✓

## Font Selection

Inter font family provides excellent readability for numerical data and maintains a professional, technical appearance suitable for enterprise tools.

- **Typographic Hierarchy**: 
  - H1 (App Title): Inter Bold/28px/tight letter spacing
  - H2 (Section Headers): Inter Semibold/20px/normal spacing
  - H3 (Subsections): Inter Medium/16px/normal spacing  
  - Body Text: Inter Regular/14px/1.5 line height
  - Numbers: Inter Medium/tabular-nums for aligned calculations
  - Small Labels: Inter Regular/12px/muted colors

## Animations

Subtle and functional animations enhance the professional feel while providing clear feedback on calculation updates without being distracting during financial planning.

- **Purposeful Meaning**: Brief highlight animations on price changes reinforce calculation accuracy and responsiveness
- **Hierarchy of Movement**: Only totals and changed values animate to draw attention to important updates

## Component Selection

- **Components**: Cards for section organization, Collapsibles for progressive disclosure, Select dropdowns for constrained choices, Input fields with validation, Switches for feature toggles, Badges for status indicators
- **Customizations**: Custom highlight animations for price updates, specialized number formatting components for currency and tokens
- **States**: Clear disabled states for PTU pricing, hover states on interactive elements, focus states with proper keyboard navigation
- **Icon Selection**: Phosphor icons with Calculator, FileText, Gear, and Warning icons representing different functional areas
- **Spacing**: Consistent 4px base unit scaling (gap-2, gap-4, gap-6) with generous padding in cards (p-4, p-6)
- **Mobile**: Responsive grid layouts that stack on mobile, collapsible sections to manage screen space, touch-friendly button sizes