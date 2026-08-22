#!/usr/bin/env python3
"""
Generate a professional, high-resolution Architecture Diagram PNG for Blue Toad Fleet.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches

def generate_diagram():
    fig, ax = plt.subplots(figsize=(16, 9), dpi=300)
    fig.patch.set_facecolor('#0f1115')
    ax.set_facecolor('#0f1115')

    # Title & Subtitle
    ax.text(8.0, 8.4, "BLUE TOAD FLEET — SYSTEM ARCHITECTURE", 
            fontsize=20, fontweight='bold', color='#e8eaf0', ha='center', va='center', fontfamily='sans-serif')
    ax.text(8.0, 8.0, "Multi-Agent Spatial Vision, Vertex AI Multimodal Routing & Serverless Bid Allocation on Google Cloud", 
            fontsize=11, color='#a78bfa', ha='center', va='center', fontfamily='sans-serif')

    def draw_box(x, y, w, h, title, subtitle, border_color, fill_color='#171a21', title_color='#e8eaf0'):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.15",
                                      linewidth=1.8, edgecolor=border_color, facecolor=fill_color)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h - 0.28, title, fontsize=11, fontweight='bold', color=title_color, ha='center', va='center')
        ax.text(x + w/2, y + h/2 - 0.12, subtitle, fontsize=8.5, color='#a7b0c0', ha='center', va='center', multialignment='center')

    def draw_arrow(x1, y1, x2, y2, color='#78829a', label=''):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(facecolor=color, edgecolor=color, width=1.5, headwidth=7, headlength=7, shrink=0.05))
        if label:
            ax.text((x1+x2)/2, (y1+y2)/2 + 0.15, label, fontsize=8, color='#38bdf8', ha='center', va='center', fontweight='bold')

    # Pillar 1: Ingestion & Spatial Graph
    draw_box(0.8, 4.5, 3.2, 2.6, "1. INTAKE & SPATIAL GRAPH", 
             "• 450+ Unlabelled Gallery Photos\n• Reconstructs 3D Pole Barn Topology\n• Margin Co-Visibility & Table Invariants\n• Merges Multi-Angle Duplicates", 
             '#38bdf8')

    # Pillar 2: Vertex AI Multi-Tier Routing
    draw_box(4.6, 5.2, 3.4, 2.2, "2A. TRIAGE FAN-OUT",
             "• Model: gemini-3.5-flash-lite\n• Fast filtering at $0.30/1M tokens\n• Discards modern filler / hardware\n• 462 photos -> 228 survivors",
             '#34d399')

    draw_box(4.6, 2.4, 3.4, 2.4, "2B. DEEP APPRAISAL",
             "• Model: gemini-3.6-flash (global)\n• Structured OpenAPI 3.0 Schemas\n• Container Lot Decomposition\n• Model Never States A Price",
             '#a78bfa')

    # Pillar 3: Deterministic BidMath
    draw_box(8.6, 3.8, 3.2, 2.6, "3. PURE BIDMATH ENGINE",
             "• 35-40% Buy-In Band (37.5% mid)\n• Condition Penalty Clamping\n• 'Buyer's Choice' Mechanic Modelling\n• Greedy Allocation vs Budget Cap\n• Refuses Lots With No Comp\n• 570 Unit Tests, 563 Pass (~5s)",
             '#fbbf24')

    # Pillar 4: Gate Console & Collaborative Partner
    draw_box(12.4, 4.5, 3.0, 2.6, "4. GATE CONSOLE (CLOUD RUN)", 
             "• Serverless on us-central1\n• Interactive 2D Showroom Map\n• Proactive Velocity Pushback\n• Cross-Cycle Keyed Memory\n• Friday 4:00 PM Operator Review", 
             '#f87171')

    # Pillar 5: Output Sourcing Execution
    draw_box(12.4, 1.2, 3.0, 2.4, "5. SOURCING EXECUTION", 
             "• Sealed Absentee Bid Email Draft\n  (info@bluetoadauctions.com)\n• $5.00 Bidding Increments\n• 15% Absentee Fee Enforced\n• Excel Sourcing Workbooks", 
             '#34d399')

    # Draw Connections
    draw_arrow(4.0, 5.8, 4.6, 6.0, '#38bdf8', '462 Photos')
    draw_arrow(4.0, 5.0, 4.6, 3.8, '#a78bfa', 'Spatial Lots')
    draw_arrow(8.0, 6.0, 8.6, 5.4, '#34d399', 'Triaged Lots')
    draw_arrow(8.0, 3.6, 8.6, 4.5, '#a78bfa', 'Appraisals')
    draw_arrow(11.8, 5.1, 12.4, 5.6, '#fbbf24', 'Allocated Bids')
    draw_arrow(13.9, 4.5, 13.9, 3.6, '#34d399', 'Approved Draft')

    # Footer Metadata
    ax.text(8.0, 0.5, "Google Cloud Stack: Vertex AI (gemini-3.6-flash, gemini-3.5-flash-lite) · Cloud Run · Artifact Registry · Cloud Build · Python 3.11",
            fontsize=9.5, color='#78829a', ha='center', va='center')

    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis('off')
    plt.tight_layout()
    
    out_path = "docs/architecture_diagram.png"
    plt.savefig(out_path, facecolor=fig.get_facecolor(), edgecolor='none')
    print(f"[✓] Architecture Diagram generated: {out_path}")

if __name__ == "__main__":
    generate_diagram()
