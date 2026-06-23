import os
import base64
import textwrap
import pandas as pd
import geopandas as gpd
import streamlit as st
import folium
import branca.colormap as cm
import plotly.express as px
import plotly.graph_objects as go
from streamlit_folium import st_folium


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="SleepMap Valencia",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# =========================================================
# FILES
# =========================================================

DATA_FILE = "barrios_sleep_green.geojson"
HERO_FILE = "valencia_night_hero.png"


# =========================================================
# HTML HELPER
# =========================================================

def html(markup):
    st.markdown(textwrap.dedent(markup).strip(), unsafe_allow_html=True)


# =========================================================
# LOAD DATA
# =========================================================

@st.cache_data
def load_data():
    gdf = gpd.read_file(DATA_FILE)
    gdf = gdf.to_crs(epsg=4326)
    return gdf


gdf = load_data()


# =========================================================
# DATA PREPARATION
# =========================================================

numeric_columns = [
    "indice_descanso_final",
    "sleep_score_medio",
    "nivel_ruido_medio",
    "porcentaje_ruido_alto_extremo",
    "vulnerability_score",
    "green_score",
    "porcentaje_zona_verde",
    "superficie_verde_m2"
]

for col in numeric_columns:
    if col in gdf.columns:
        gdf[col] = pd.to_numeric(gdf[col], errors="coerce")


category_translation = {
    "Muy favorable": "Very favourable",
    "Favorable": "Favourable",
    "Intermedio": "Intermediate",
    "Desfavorable": "Unfavourable",
    "Crítico": "Critical",
    "Sin datos": "No data"
}

gdf["urban_rest_category"] = (
    gdf["categoria_descanso_final"]
    .map(category_translation)
    .fillna(gdf["categoria_descanso_final"])
)


# =========================================================
# GLOBAL OPTIONS
# =========================================================

all_categories = sorted(gdf["urban_rest_category"].dropna().unique())
all_neighbourhoods = sorted(gdf["nombre"].dropna().unique())

category_order = [
    "Very favourable",
    "Favourable",
    "Intermediate",
    "Unfavourable",
    "Critical",
    "No data"
]

category_order = [cat for cat in category_order if cat in all_categories]

category_color_map = {
    "Very favourable": "#15803d",
    "Favourable": "#8da0cb",
    "Intermediate": "#66c2a5",
    "Unfavourable": "#fc8d62",
    "Critical": "#b91c1c",
    "No data": "#9ca3af"
}

map_options = {
    "Dynamic Urban Rest Index": "dynamic_index",
    "Acoustic quality": "sleep_score_medio",
    "Average night-time noise": "nivel_ruido_medio",
    "High/extreme noise exposure": "porcentaje_ruido_alto_extremo",
    "Green area percentage": "porcentaje_zona_verde"
}

indicator_explanations = {
    "Dynamic Urban Rest Index": (
        "Global score combining acoustic quality, social vulnerability and green areas. "
        "Higher values mean better conditions for night-time rest."
    ),
    "Acoustic quality": (
        "Score derived from night-time noise. Higher values mean better acoustic conditions."
    ),
    "Average night-time noise": (
        "Average night-time noise level by neighbourhood. Higher values mean worse noise conditions."
    ),
    "High/extreme noise exposure": (
        "Percentage of each neighbourhood affected by high or extreme night-time noise. "
        "Higher values mean worse exposure."
    ),
    "Green area percentage": (
        "Percentage of the neighbourhood covered by green areas. Higher values mean more green infrastructure."
    )
}

label_mode_options = [
    "None",
    "Highlighted only",
    "Custom selection",
    "All visible neighbourhoods"
]


# =========================================================
# SESSION STATE DEFAULTS
# =========================================================

defaults = {
    "noise_weight": 60,
    "vulnerability_weight": 20,
    "map_indicator_label": "Dynamic Urban Rest Index",
    "selected_categories": all_categories,
    "highlighted_neighbourhoods": [],
    "label_mode": "Highlighted only",
    "custom_labels": [],
    "top_n": 10,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# STATE SANITISING
# =========================================================

def sanitise_state():
    if st.session_state["map_indicator_label"] not in map_options:
        st.session_state["map_indicator_label"] = "Dynamic Urban Rest Index"

    st.session_state["selected_categories"] = [
        c for c in st.session_state["selected_categories"]
        if c in all_categories
    ]

    if len(st.session_state["selected_categories"]) == 0:
        st.session_state["selected_categories"] = all_categories

    st.session_state["highlighted_neighbourhoods"] = [
        n for n in st.session_state["highlighted_neighbourhoods"]
        if n in all_neighbourhoods
    ]

    st.session_state["custom_labels"] = [
        n for n in st.session_state["custom_labels"]
        if n in all_neighbourhoods
    ]

    if st.session_state["label_mode"] not in label_mode_options:
        st.session_state["label_mode"] = "Highlighted only"

    st.session_state["top_n"] = max(5, min(20, int(st.session_state["top_n"])))
    st.session_state["noise_weight"] = max(30, min(80, int(st.session_state["noise_weight"])))
    st.session_state["vulnerability_weight"] = max(0, min(50, int(st.session_state["vulnerability_weight"])))


sanitise_state()


# =========================================================
# MIRRORED CONTROL STATE
# =========================================================

CONTROL_PREFIXES = ["map", "rankings"]

CONTROL_FIELDS = [
    "noise_weight",
    "vulnerability_weight",
    "map_indicator_label",
    "selected_categories",
    "highlighted_neighbourhoods",
    "label_mode",
    "custom_labels",
    "top_n"
]


def init_control_keys():
    for prefix in CONTROL_PREFIXES:
        for field in CONTROL_FIELDS:
            widget_key = f"{prefix}_{field}"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = st.session_state[field]


def sync_mirrors_from_main():
    for prefix in CONTROL_PREFIXES:
        for field in CONTROL_FIELDS:
            st.session_state[f"{prefix}_{field}"] = st.session_state[field]


def sync_controls_from(prefix):
    for field in CONTROL_FIELDS:
        st.session_state[field] = st.session_state[f"{prefix}_{field}"]

    sanitise_state()
    sync_mirrors_from_main()


init_control_keys()
sync_mirrors_from_main()


# =========================================================
# HELPERS
# =========================================================

def image_to_base64(path):
    if not os.path.exists(path):
        return None

    with open(path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()


def format_value(x, decimals=2):
    if pd.isna(x):
        return "No data"
    return round(float(x), decimals)


def card_html(title, value, note="", accent_color="#dc2626", value_color="#111827"):
    return f"""
    <div class="custom-card" style="border-top:4px solid {accent_color};">
        <div class="card-title">{title}</div>
        <div class="card-value" style="color:{value_color};">{value}</div>
        <div class="card-note">{note}</div>
    </div>
    """


def section_title(title, subtitle=""):
    subtitle_html = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    return f"""
    <div class="section-wrap">
        {subtitle_html}
        <div class="section-title">{title}</div>
    </div>
    """


def style_plot(fig):
    fig.update_layout(
        template="simple_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(color="#1f2937"),
        title_font=dict(size=18, color="#111827"),
        margin=dict(l=25, r=25, t=55, b=25),
        legend=dict(
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="#e5e7eb"
        )
    )
    return fig


def compute_dynamic_index(dataframe, noise_weight, vulnerability_weight, green_weight):
    df = dataframe.copy()
    df["dynamic_index"] = df["indice_descanso_final"]

    mask_vulnerability = df["vulnerability_score"].notna()

    df.loc[mask_vulnerability, "dynamic_index"] = (
        (noise_weight / 100) * df.loc[mask_vulnerability, "sleep_score_medio"]
        + (vulnerability_weight / 100) * df.loc[mask_vulnerability, "vulnerability_score"]
        + (green_weight / 100) * df.loc[mask_vulnerability, "green_score"]
    )

    denominator = noise_weight + green_weight

    if denominator == 0:
        noise_weight_no_vul = 1
        green_weight_no_vul = 0
    else:
        noise_weight_no_vul = noise_weight / denominator
        green_weight_no_vul = green_weight / denominator

    df.loc[~mask_vulnerability, "dynamic_index"] = (
        noise_weight_no_vul * df.loc[~mask_vulnerability, "sleep_score_medio"]
        + green_weight_no_vul * df.loc[~mask_vulnerability, "green_score"]
    )

    df["dynamic_index"] = df["dynamic_index"].round(2)
    return df


def add_labels_to_map(map_object, label_gdf, text_color="#111827", background="rgba(255,255,255,0.82)"):
    if len(label_gdf) == 0:
        return

    labels_data = label_gdf.copy()
    label_points = labels_data.geometry.representative_point()
    labels_data["lat"] = label_points.y
    labels_data["lon"] = label_points.x

    for _, row in labels_data.iterrows():
        folium.Marker(
            location=[row["lat"], row["lon"]],
            icon=folium.DivIcon(
                html=f"""
                <div style="
                    font-size:10px;
                    font-weight:800;
                    color:{text_color};
                    background:{background};
                    padding:2px 5px;
                    border-radius:4px;
                    white-space:nowrap;
                    text-align:center;
                    box-shadow:0 1px 4px rgba(0,0,0,0.18);">
                    {row['nombre']}
                </div>
                """
            )
        ).add_to(map_object)


def build_ranking_map(data, ranking_type="best"):
    if ranking_type == "best":
        colors = ["#dcfce7", "#86efac", "#22c55e", "#15803d"]
        border_color = "#166534"
        caption = "Highest scoring neighbourhoods"
    else:
        colors = ["#fee2e2", "#fca5a5", "#ef4444", "#991b1b"]
        border_color = "#7f1d1d"
        caption = "Lowest scoring neighbourhoods"

    if len(data) == 0:
        return None

    min_value = data["dynamic_index"].min()
    max_value = data["dynamic_index"].max()

    if pd.isna(min_value) or pd.isna(max_value):
        min_value = 0
        max_value = 1

    if min_value == max_value:
        max_value = min_value + 1

    colormap = cm.LinearColormap(
        colors=colors,
        vmin=min_value,
        vmax=max_value,
        caption=caption
    )

    m = folium.Map(
        location=[39.47, -0.37],
        zoom_start=12,
        tiles="cartodbpositron"
    )

    def style_function(feature):
        value = feature["properties"].get("dynamic_index")

        if value is None or pd.isna(value):
            fill_color = "#d1d5db"
        else:
            fill_color = colormap(value)

        return {
            "fillColor": fill_color,
            "color": border_color,
            "weight": 2.2,
            "fillOpacity": 0.78
        }

    tooltip = folium.GeoJsonTooltip(
        fields=[
            "nombre",
            "dynamic_index",
            "urban_rest_category",
            "sleep_score_medio",
            "nivel_ruido_medio",
            "porcentaje_zona_verde",
            "vul_global"
        ],
        aliases=[
            "Neighbourhood:",
            "Dynamic index:",
            "Category:",
            "Acoustic quality:",
            "Noise level:",
            "Green area (%):",
            "Vulnerability:"
        ],
        localize=True,
        sticky=True
    )

    folium.GeoJson(
        data,
        name=caption,
        style_function=style_function,
        tooltip=tooltip
    ).add_to(m)

    add_labels_to_map(m, data)

    colormap.add_to(m)

    return m


def render_analysis_controls(prefix):
    html(
        """
        <div class="controls-intro">
            <b>Configure the analysis</b><br>
            Choose what is displayed on the map and adjust the weights of the dynamic index.
        </div>
        """
    )

    col1, col2, col3 = st.columns([1.05, 1.15, 1])

    with col1:
        st.markdown("#### Index weights")

        st.slider(
            "Noise importance (%)",
            min_value=30,
            max_value=80,
            step=5,
            key=f"{prefix}_noise_weight",
            on_change=sync_controls_from,
            args=(prefix,)
        )

        st.slider(
            "Low vulnerability importance (%)",
            min_value=0,
            max_value=50,
            step=5,
            key=f"{prefix}_vulnerability_weight",
            on_change=sync_controls_from,
            args=(prefix,)
        )

        current_green_weight = (
            100
            - st.session_state[f"{prefix}_noise_weight"]
            - st.session_state[f"{prefix}_vulnerability_weight"]
        )

        st.metric("Green areas importance (%)", current_green_weight)

        html(
            f"""
            <div class="small-help">
                Calculated as the remaining percentage:<br>
                <b>100 - {st.session_state[f"{prefix}_noise_weight"]} - {st.session_state[f"{prefix}_vulnerability_weight"]} = {current_green_weight}%</b>
            </div>
            """
        )

    with col2:
        st.markdown("#### Map content")

        st.selectbox(
            "Map indicator",
            list(map_options.keys()),
            key=f"{prefix}_map_indicator_label",
            on_change=sync_controls_from,
            args=(prefix,)
        )

        selected_indicator = st.session_state[f"{prefix}_map_indicator_label"]

        html(
            f"""
            <div class="small-help">
                {indicator_explanations[selected_indicator]}
            </div>
            """
        )

        st.multiselect(
            "Urban rest category",
            options=all_categories,
            key=f"{prefix}_selected_categories",
            on_change=sync_controls_from,
            args=(prefix,)
        )

        st.multiselect(
            "Highlighted neighbourhoods",
            options=all_neighbourhoods,
            key=f"{prefix}_highlighted_neighbourhoods",
            help="Selected neighbourhoods will have a thicker border on the map.",
            on_change=sync_controls_from,
            args=(prefix,)
        )

    with col3:
        st.markdown("#### Labels and ranking")

        st.selectbox(
            "Neighbourhood labels",
            options=label_mode_options,
            key=f"{prefix}_label_mode",
            on_change=sync_controls_from,
            args=(prefix,)
        )

        label_mode = st.session_state[f"{prefix}_label_mode"]

        if label_mode == "Custom selection":
            st.multiselect(
                "Choose labels to display",
                options=all_neighbourhoods,
                key=f"{prefix}_custom_labels",
                on_change=sync_controls_from,
                args=(prefix,)
            )
        else:
            st.session_state[f"{prefix}_custom_labels"] = []
            st.session_state["custom_labels"] = []

        st.slider(
            "Ranking size",
            min_value=5,
            max_value=20,
            step=1,
            key=f"{prefix}_top_n",
            on_change=sync_controls_from,
            args=(prefix,)
        )


def get_current_filtered_data():
    noise_weight = st.session_state["noise_weight"]
    vulnerability_weight = st.session_state["vulnerability_weight"]
    green_weight = 100 - noise_weight - vulnerability_weight

    if green_weight < 0:
        st.error("The total weight exceeds 100%. Reduce one of the weights.")
        st.stop()

    current = compute_dynamic_index(gdf, noise_weight, vulnerability_weight, green_weight)

    filtered = current[
        current["urban_rest_category"].isin(st.session_state["selected_categories"])
    ].copy()

    if len(filtered) == 0:
        st.warning("No neighbourhoods match the selected filters.")
        st.stop()

    return current, filtered, green_weight


# =========================================================
# COMPUTE CURRENT DATA
# =========================================================

gdf_current, gdf_filtered, green_weight = get_current_filtered_data()
selected_map_label = st.session_state["map_indicator_label"]
map_variable = map_options[selected_map_label]


# =========================================================
# CUSTOM CSS
# =========================================================

html(
    """
    <style>
    header[data-testid="stHeader"],
    div[data-testid="stToolbar"],
    div[data-testid="stDecoration"],
    #MainMenu,
    footer,
    section[data-testid="stSidebar"] {
        display: none !important;
        visibility: hidden !important;
    }

    .stApp {
        background: #f8fafc;
        color: #111827;
    }

    .block-container {
        max-width: 1520px;
        padding-top: 1.1rem;
        padding-bottom: 2rem;
    }

    .topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 20px;
        border-radius: 22px;
        background: #ffffff;
        border: 1px solid #e5e7eb;
        box-shadow: 0 8px 24px rgba(0,0,0,0.05);
        margin-bottom: 18px;
    }

    .brand-wrap {
        display: flex;
        align-items: center;
        gap: 14px;
    }

    .brand-logo {
        width: 54px;
        height: 54px;
        border-radius: 17px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #fff1f2;
        color: #be123c;
        border: 1px solid #fecdd3;
        font-size: 26px;
        font-weight: 800;
    }

    .brand-title {
        font-size: 30px;
        font-weight: 900;
        color: #111827;
        line-height: 1;
        letter-spacing: -0.7px;
    }

    .brand-subtitle {
        font-size: 13px;
        color: #6b7280;
        margin-top: 5px;
    }

    .status-badge {
        background: #fff1f2;
        color: #be123c;
        border: 1px solid #fecdd3;
        border-radius: 999px;
        padding: 8px 14px;
        font-size: 13px;
        font-weight: 700;
    }

    button[data-baseweb="tab"] {
        background: #ffffff;
        color: #374151;
        border-radius: 14px 14px 0 0;
        border: 1px solid #e5e7eb;
        padding: 12px 18px;
        font-weight: 700;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        background: #dc2626;
        color: white;
        border-color: #dc2626;
    }

    .section-wrap {
        margin-top: 22px;
        margin-bottom: 14px;
    }

    .section-subtitle {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #6b7280;
        margin-bottom: 4px;
        font-weight: 700;
    }

    .section-title {
        font-size: 28px;
        font-weight: 900;
        color: #111827;
    }

    .custom-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 20px;
        padding: 20px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.04);
        min-height: 120px;
    }

    .card-title {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #6b7280;
        margin-bottom: 8px;
        font-weight: 800;
    }

    .card-value {
        font-size: 30px;
        font-weight: 900;
        margin-bottom: 4px;
        line-height: 1.15;
    }

    .card-note {
        font-size: 13px;
        color: #6b7280;
        line-height: 1.45;
    }

    .info-box {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 18px;
        padding: 20px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.04);
        min-height: 155px;
    }

    .controls-intro {
        background: #fff7f7;
        border: 1px solid #fecaca;
        border-left: 5px solid #dc2626;
        border-radius: 16px;
        padding: 16px 18px;
        color: #374151;
        margin-bottom: 18px;
        line-height: 1.55;
    }

    .small-help {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 10px 12px;
        color: #6b7280;
        font-size: 13px;
        line-height: 1.55;
        margin: 8px 0 18px 0;
    }

    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 18px;
        padding: 16px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.04);
    }

    div[data-testid="stMetricValue"] {
        color: #111827;
        font-weight: 900;
    }

    div[data-testid="stMetricLabel"] {
        color: #6b7280;
    }

    .map-box {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 22px;
        padding: 12px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.04);
    }

    .hero-section {
        min-height: 470px;
        border-radius: 22px;
        overflow: hidden;
        background-size: cover;
        background-position: center;
        box-shadow: 0 12px 32px rgba(15,23,42,0.18);
        border: 1px solid #e5e7eb;
        margin-top: 18px;
        margin-bottom: 22px;
        position: relative;
    }

    .hero-content {
        padding: 42px 46px;
        max-width: 500px;
        color: white;
    }

    .hero-title {
        font-size: 48px;
        font-weight: 950;
        line-height: 1.03;
        letter-spacing: -1.2px;
        margin-bottom: 16px;
        text-shadow: 0 3px 14px rgba(0,0,0,0.32);
    }

    .hero-subtitle {
        font-size: 20px;
        font-weight: 800;
        line-height: 1.35;
        margin-bottom: 18px;
        text-shadow: 0 2px 10px rgba(0,0,0,0.28);
    }

    .hero-text {
        font-size: 15px;
        line-height: 1.55;
        max-width: 455px;
        color: rgba(255,255,255,0.92);
        margin-bottom: 20px;
    }

    .hero-chip {
        display: inline-flex;
        align-items: center;
        background: rgba(255,255,255,0.93);
        color: #111827;
        border: 1px solid rgba(255,255,255,0.65);
        border-radius: 999px;
        padding: 8px 13px;
        margin-right: 8px;
        margin-bottom: 10px;
        font-size: 13px;
        font-weight: 800;
        box-shadow: 0 6px 16px rgba(0,0,0,0.16);
    }

    .chip-red { color: #b91c1c; }
    .chip-orange { color: #c2410c; }
    .chip-green { color: #166534; }
    .chip-blue { color: #1d4ed8; }

    .hero-metrics-row {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 18px;
        margin-top: -4px;
        margin-bottom: 26px;
    }

    .hero-metric-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-top: 4px solid #dc2626;
        border-radius: 18px;
        padding: 22px 24px;
        box-shadow: 0 8px 24px rgba(15,23,42,0.06);
    }

    .hero-metric-number {
        font-size: 36px;
        font-weight: 950;
        color: #111827;
        line-height: 1;
        margin-bottom: 8px;
    }

    .hero-metric-label {
        font-size: 14px;
        color: #6b7280;
        font-weight: 700;
    }

    .home-section-heading {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 24px 0 14px 0;
    }

    .home-section-bar {
        width: 5px;
        height: 28px;
        border-radius: 99px;
        background: #dc2626;
    }

    .home-section-title {
        font-size: 27px;
        font-weight: 950;
        color: #111827;
        letter-spacing: -0.4px;
    }

    .show-card {
        display: flex;
        gap: 18px;
        align-items: center;
        background: white;
        border-radius: 18px;
        padding: 22px 24px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 8px 22px rgba(15,23,42,0.05);
        min-height: 128px;
    }

    .show-icon {
        width: 58px;
        height: 58px;
        border-radius: 999px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        font-size: 26px;
    }

    .show-icon-red {
        background: #fee2e2;
        border: 2px solid #fecaca;
    }

    .show-icon-orange {
        background: #ffedd5;
        border: 2px solid #fed7aa;
    }

    .show-icon-green {
        background: #dcfce7;
        border: 2px solid #bbf7d0;
    }

    .show-title {
        font-size: 19px;
        font-weight: 900;
        margin-bottom: 7px;
        color: #111827;
    }

    .show-text {
        color: #4b5563;
        font-size: 14px;
        line-height: 1.5;
    }

    .formula-card {
        background: white;
        border: 1px solid #fecaca;
        border-radius: 22px;
        padding: 26px;
        box-shadow: 0 8px 24px rgba(15,23,42,0.05);
        min-height: 360px;
    }

    .formula-title-small {
        font-size: 14px;
        color: #6b7280;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 18px;
    }

    .formula-row {
        display: flex;
        align-items: center;
        gap: 16px;
        flex-wrap: wrap;
    }

    .formula-main {
        width: 165px;
        min-height: 126px;
        border-radius: 18px;
        border: 2px solid #ef4444;
        background: linear-gradient(135deg, #fff1f2, #ffffff);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: #b91c1c;
        text-align: center;
        font-weight: 950;
        font-size: 22px;
        line-height: 1.1;
    }

    .formula-symbol {
        font-size: 32px;
        font-weight: 900;
        color: #374151;
    }

    .formula-component {
        width: 135px;
        min-height: 86px;
        border-radius: 14px;
        border: 1px solid #fecaca;
        background: #fff7f7;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        color: #111827;
        font-weight: 800;
        font-size: 14px;
        line-height: 1.2;
    }

    .formula-component.orange {
        background: #fff7ed;
        border-color: #fed7aa;
    }

    .formula-component.green {
        background: #f0fdf4;
        border-color: #bbf7d0;
    }

    .formula-note {
        margin-top: 22px;
        border-radius: 14px;
        border: 1px solid #fecaca;
        background: #fff7f7;
        padding: 14px 18px;
        color: #374151;
        font-weight: 700;
        text-align: center;
    }

    .footer-note {
        margin-top: 30px;
        padding: 18px;
        text-align: center;
        color: #6b7280;
        font-size: 13px;
        border-top: 1px solid #e5e7eb;
    }
    </style>
    """
)


# =========================================================
# TOP BAR
# =========================================================

html(
    """
    <div class="topbar">
        <div class="brand-wrap">
            <div class="brand-logo">🌙</div>
            <div>
                <div class="brand-title">SleepMap Valencia</div>
                <div class="brand-subtitle">Interactive urban rest analysis by neighbourhood</div>
            </div>
        </div>
        <div class="status-badge">Urban Rest App</div>
    </div>
    """
)


# =========================================================
# TABS
# =========================================================

tab_home, tab_map, tab_rankings, tab_insights = st.tabs(
    ["Home", "Map", "Rankings", "Insights"]
)


# =========================================================
# HOME
# =========================================================

with tab_home:
    hero_b64 = image_to_base64(HERO_FILE)

    if hero_b64 is not None:
        hero_background = (
            "linear-gradient(90deg, rgba(4,10,25,0.86) 0%, "
            "rgba(4,10,25,0.64) 28%, rgba(4,10,25,0.16) 52%, "
            "rgba(4,10,25,0.02) 100%), "
            f"url('data:image/png;base64,{hero_b64}')"
        )
    else:
        hero_background = (
            "linear-gradient(135deg, #020617 0%, #1e293b 55%, #334155 100%)"
        )

    html(
        f"""
        <div class="hero-section" style="background-image: {hero_background};">
            <div class="hero-content">
                <div class="hero-title">Where does Valencia<br>rest better?</div>
                <div class="hero-subtitle">
                    A city can be vibrant and still protect the right to rest.
                </div>
                <div class="hero-text">
                    Explore how night-time noise, urban vulnerability and green infrastructure
                    shape rest conditions across Valencia neighbourhoods.
                </div>
                <div>
                    <span class="hero-chip chip-red">Noise exposure</span>
                    <span class="hero-chip chip-orange">Urban vulnerability</span>
                    <span class="hero-chip chip-green">Green infrastructure</span>
                    <span class="hero-chip chip-blue">Open data</span>
                </div>
            </div>
        </div>
        """
    )

    html(
        f"""
        <div class="hero-metrics-row">
            <div class="hero-metric-card">
                <div class="hero-metric-number">{len(gdf)}</div>
                <div class="hero-metric-label">Neighbourhoods analysed</div>
            </div>
            <div class="hero-metric-card">
                <div class="hero-metric-number">3</div>
                <div class="hero-metric-label">Urban dimensions</div>
            </div>
            <div class="hero-metric-card">
                <div class="hero-metric-number">1</div>
                <div class="hero-metric-label">Dynamic Urban Rest Index</div>
            </div>
        </div>
        """
    )

    html(
        """
        <div class="home-section-heading">
            <div class="home-section-bar"></div>
            <div class="home-section-title">What does SleepMap show?</div>
        </div>
        """
    )

    s1, s2, s3 = st.columns(3)

    with s1:
        html(
            """
            <div class="show-card">
                <div class="show-icon show-icon-red">🔊</div>
                <div>
                    <div class="show-title" style="color:#dc2626;">Noise pressure</div>
                    <div class="show-text">
                        Night-time noise exposure from traffic, leisure and urban activity
                        across neighbourhoods.
                    </div>
                </div>
            </div>
            """
        )

    with s2:
        html(
            """
            <div class="show-card">
                <div class="show-icon show-icon-orange">👥</div>
                <div>
                    <div class="show-title" style="color:#ea580c;">Social vulnerability</div>
                    <div class="show-text">
                        Socio-economic factors that can increase sensitivity to noise
                        and reduce rest quality.
                    </div>
                </div>
            </div>
            """
        )

    with s3:
        html(
            """
            <div class="show-card">
                <div class="show-icon show-icon-green">🌿</div>
                <div>
                    <div class="show-title" style="color:#15803d;">Green infrastructure</div>
                    <div class="show-text">
                        Access to green spaces is included as a positive factor for
                        healthier night-time rest.
                    </div>
                </div>
            </div>
            """
        )

    html(
        """
        <div class="home-section-heading">
            <div class="home-section-bar"></div>
            <div class="home-section-title">How the Urban Rest Index works</div>
        </div>
        """
    )

    f_col, w_col = st.columns([1.25, 0.9])

    with f_col:
        html(
            """
            <div class="formula-card">
                <div class="formula-title-small">Index structure</div>
                <div class="formula-row">
                    <div class="formula-main">
                        Urban Rest<br>Index
                    </div>
                    <div class="formula-symbol">=</div>
                    <div class="formula-component">
                        Acoustic<br>quality
                    </div>
                    <div class="formula-symbol">+</div>
                    <div class="formula-component orange">
                        Low<br>vulnerability
                    </div>
                    <div class="formula-symbol">+</div>
                    <div class="formula-component green">
                        Green<br>score
                    </div>
                </div>
                <div class="formula-note">
                    Higher values mean better night-time rest conditions.
                </div>
            </div>
            """
        )

    with w_col:
        with st.container(border=True):
            st.markdown("### Weighting details")

            st.markdown("**Neighbourhoods with vulnerability data**")

            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown("Acoustic quality")
                st.markdown("Low vulnerability")
                st.markdown("Green score")
            with c2:
                st.markdown("**50%**")
                st.markdown("**25%**")
                st.markdown("**25%**")

            st.divider()

            st.markdown("**Neighbourhoods without vulnerability data**")

            c3, c4 = st.columns([2, 1])
            with c3:
                st.markdown("Acoustic quality")
                st.markdown("Green score")
            with c4:
                st.markdown("**75%**")
                st.markdown("**25%**")

            st.info(
                "The dynamic version allows these weights to be adjusted interactively "
                "in the Map and Rankings tabs."
            )

    html(
        """
        <div class="footer-note">
            Built with open data for a more restful Valencia · SleepMap Valencia is an exploratory urban data project.
        </div>
        """
    )


# =========================================================
# MAP
# =========================================================

with tab_map:
    html(section_title("Interactive map", "Main analysis view"))

    with st.expander("Analysis controls", expanded=True):
        render_analysis_controls("map")

    gdf_current, gdf_filtered, green_weight = get_current_filtered_data()
    selected_map_label = st.session_state["map_indicator_label"]
    map_variable = map_options[selected_map_label]

    map_data = gdf_filtered.copy()
    highlighted_set = set(st.session_state["highlighted_neighbourhoods"])

    min_value = map_data[map_variable].min()
    max_value = map_data[map_variable].max()

    if pd.isna(min_value) or pd.isna(max_value):
        min_value = 0
        max_value = 1

    if min_value == max_value:
        max_value = min_value + 1

    if map_variable in ["nivel_ruido_medio", "porcentaje_ruido_alto_extremo"]:
        colormap = cm.LinearColormap(
            colors=["#2563eb", "#38bdf8", "#fde68a", "#fb923c", "#ef4444", "#7f1d1d"],
            vmin=min_value,
            vmax=max_value,
            caption=selected_map_label
        )
    else:
        colormap = cm.LinearColormap(
            colors=["#7f1d1d", "#ef4444", "#fb923c", "#fde68a", "#86efac", "#38bdf8", "#2563eb"],
            vmin=min_value,
            vmax=max_value,
            caption=selected_map_label
        )

    m = folium.Map(
        location=[39.47, -0.37],
        zoom_start=12,
        tiles="cartodbpositron"
    )

    def style_function(feature):
        value = feature["properties"].get(map_variable)
        neighbourhood_name = feature["properties"].get("nombre")

        if value is None or pd.isna(value):
            fill_color = "#d1d5db"
        else:
            fill_color = colormap(value)

        if neighbourhood_name in highlighted_set:
            border_color = "#111827"
            border_weight = 3.5
        else:
            border_color = "#374151"
            border_weight = 0.8

        return {
            "fillColor": fill_color,
            "color": border_color,
            "weight": border_weight,
            "fillOpacity": 0.78
        }

    tooltip = folium.GeoJsonTooltip(
        fields=[
            "nombre",
            "dynamic_index",
            "urban_rest_category",
            "sleep_score_medio",
            "nivel_ruido_medio",
            "porcentaje_ruido_alto_extremo",
            "vul_global",
            "porcentaje_zona_verde"
        ],
        aliases=[
            "Neighbourhood:",
            "Dynamic index:",
            "Category:",
            "Acoustic quality:",
            "Noise level:",
            "High/extreme noise (%):",
            "Vulnerability:",
            "Green area (%):"
        ],
        localize=True,
        sticky=True
    )

    folium.GeoJson(
        map_data,
        name="Neighbourhoods",
        style_function=style_function,
        tooltip=tooltip
    ).add_to(m)

    label_mode = st.session_state["label_mode"]

    if label_mode == "None":
        labels_to_show = set()
    elif label_mode == "Highlighted only":
        labels_to_show = highlighted_set
    elif label_mode == "Custom selection":
        labels_to_show = set(st.session_state["custom_labels"])
    else:
        labels_to_show = set(map_data["nombre"])

    if len(labels_to_show) > 0:
        labels_data = map_data[map_data["nombre"].isin(labels_to_show)].copy()
        add_labels_to_map(m, labels_data)

    colormap.add_to(m)

    left, right = st.columns([3.2, 1])

    with left:
        html("<div class='map-box'>")
        st_folium(m, use_container_width=True, height=700)
        html("</div>")

    with right:
        lowest = map_data.sort_values("dynamic_index", ascending=True).iloc[0]
        highest = map_data.sort_values("dynamic_index", ascending=False).iloc[0]

        html(
            card_html(
                "Selected indicator",
                selected_map_label,
                indicator_explanations[selected_map_label],
                accent_color="#dc2626"
            )
        )

        st.write("")

        html(
            card_html(
                "Lowest scoring area",
                lowest["nombre"],
                f"Dynamic index: {lowest['dynamic_index']}",
                accent_color="#dc2626",
                value_color="#dc2626"
            )
        )

        st.write("")

        html(
            card_html(
                "Highest scoring area",
                highest["nombre"],
                f"Dynamic index: {highest['dynamic_index']}",
                accent_color="#16a34a",
                value_color="#16a34a"
            )
        )

        st.write("")

        html(
            """
            <div class="info-box">
                <b>Interpretation</b><br><br>
                A <b>higher Dynamic Urban Rest Index</b> indicates more favourable
                night-time rest conditions.
            </div>
            """
        )


# =========================================================
# RANKINGS
# =========================================================

with tab_rankings:
    html(section_title("Ranking maps", "Where are the best and worst areas?"))

    with st.expander("Analysis controls", expanded=True):
        render_analysis_controls("rankings")

    gdf_current, gdf_filtered, green_weight = get_current_filtered_data()

    st.info(
        "These ranking maps are dynamic. They update automatically according to the weights and filters selected here or in the Map tab."
    )

    top_n = st.session_state["top_n"]

    best = gdf_filtered.sort_values("dynamic_index", ascending=False).head(top_n).copy()
    worst = gdf_filtered.sort_values("dynamic_index", ascending=True).head(top_n).copy()

    r1, r2 = st.columns(2)

    with r1:
        st.markdown("### Highest scoring neighbourhoods")
        best_map = build_ranking_map(best, ranking_type="best")
        st_folium(best_map, use_container_width=True, height=520)

    with r2:
        st.markdown("### Lowest scoring neighbourhoods")
        worst_map = build_ranking_map(worst, ranking_type="worst")
        st_folium(worst_map, use_container_width=True, height=520)

    html(section_title("Key ranking results", "Current scenario"))

    k1, k2, k3 = st.columns(3)

    highest = best.iloc[0]
    lowest = worst.iloc[0]
    gap = highest["dynamic_index"] - lowest["dynamic_index"]

    with k1:
        html(
            card_html(
                "Best area",
                highest["nombre"],
                f"Dynamic index: {highest['dynamic_index']}",
                accent_color="#16a34a",
                value_color="#16a34a"
            )
        )

    with k2:
        html(
            card_html(
                "Worst area",
                lowest["nombre"],
                f"Dynamic index: {lowest['dynamic_index']}",
                accent_color="#dc2626",
                value_color="#dc2626"
            )
        )

    with k3:
        html(
            card_html(
                "Index gap",
                format_value(gap),
                "Difference between best and worst area",
                accent_color="#f97316"
            )
        )


# =========================================================
# INSIGHTS
# =========================================================

with tab_insights:
    html(section_title("Insights", "Patterns and relationships"))

    st.info("These charts also use the current analysis settings from the Map tab or the Rankings tab.")

    gdf_current, gdf_filtered, green_weight = get_current_filtered_data()

    i1, i2 = st.columns(2)

    with i1:
        categories = gdf_filtered["urban_rest_category"].value_counts().reset_index()
        categories.columns = ["Urban rest category", "Number of neighbourhoods"]

        categories["Urban rest category"] = pd.Categorical(
            categories["Urban rest category"],
            categories=category_order,
            ordered=True
        )
        categories = categories.sort_values("Urban rest category")

        fig_cat = px.bar(
            categories,
            x="Urban rest category",
            y="Number of neighbourhoods",
            color="Urban rest category",
            text="Number of neighbourhoods",
            title="Neighbourhoods by urban rest category",
            labels={
                "Urban rest category": "Urban rest category",
                "Number of neighbourhoods": "Number of neighbourhoods"
            },
            color_discrete_map=category_color_map,
            category_orders={"Urban rest category": category_order}
        )
        fig_cat.update_layout(showlegend=False)
        fig_cat = style_plot(fig_cat)
        st.plotly_chart(fig_cat, use_container_width=True)

    with i2:
        fig_scatter = px.scatter(
            gdf_filtered,
            x="sleep_score_medio",
            y="dynamic_index",
            size="porcentaje_zona_verde",
            color="urban_rest_category",
            hover_name="nombre",
            title="Acoustic quality and dynamic index",
            labels={
                "sleep_score_medio": "Acoustic quality",
                "dynamic_index": "Dynamic Urban Rest Index",
                "porcentaje_zona_verde": "Green area (%)",
                "urban_rest_category": "Category"
            },
            color_discrete_map=category_color_map,
            category_orders={"urban_rest_category": category_order}
        )
        fig_scatter = style_plot(fig_scatter)
        st.plotly_chart(fig_scatter, use_container_width=True)

    i3, i4 = st.columns(2)

    with i3:
        fig_noise_box = px.box(
            gdf_filtered,
            x="urban_rest_category",
            y="nivel_ruido_medio",
            color="urban_rest_category",
            points="all",
            title="Night-time noise by urban rest category",
            labels={
                "urban_rest_category": "Urban rest category",
                "nivel_ruido_medio": "Average night-time noise score"
            },
            color_discrete_map=category_color_map,
            category_orders={"urban_rest_category": category_order}
        )
        fig_noise_box.update_layout(showlegend=False)
        fig_noise_box = style_plot(fig_noise_box)
        st.plotly_chart(fig_noise_box, use_container_width=True)

        st.caption(
            "This chart compares the distribution of average night-time noise scores across urban rest categories."
        )

    with i4:
        profile_data = gdf_filtered.copy()
        profile_data["Low high-noise exposure"] = (
            100 - profile_data["porcentaje_ruido_alto_extremo"]
        )

        profile_summary = (
            profile_data
            .groupby("urban_rest_category")
            .agg({
                "sleep_score_medio": "mean",
                "vulnerability_score": "mean",
                "green_score": "mean",
                "Low high-noise exposure": "mean",
                "dynamic_index": "mean"
            })
            .reset_index()
            .rename(columns={
                "sleep_score_medio": "Acoustic quality",
                "vulnerability_score": "Low vulnerability",
                "green_score": "Green score",
                "dynamic_index": "Dynamic index"
            })
        )

        profile_summary["urban_rest_category"] = pd.Categorical(
            profile_summary["urban_rest_category"],
            categories=category_order,
            ordered=True
        )
        profile_summary = profile_summary.sort_values("urban_rest_category")

        profile_long = profile_summary.melt(
            id_vars="urban_rest_category",
            value_vars=[
                "Acoustic quality",
                "Low vulnerability",
                "Green score",
                "Low high-noise exposure",
                "Dynamic index"
            ],
            var_name="Indicator",
            value_name="Average score"
        ).dropna()

        fig_profile = px.line(
            profile_long,
            x="Indicator",
            y="Average score",
            color="urban_rest_category",
            markers=True,
            title="Average urban rest profile by category",
            labels={
                "urban_rest_category": "Category",
                "Average score": "Average score",
                "Indicator": "Indicator"
            },
            color_discrete_map=category_color_map,
            category_orders={"urban_rest_category": category_order}
        )

        fig_profile.update_traces(line=dict(width=3), marker=dict(size=9))
        fig_profile.update_layout(yaxis_range=[0, 100])
        fig_profile = style_plot(fig_profile)

        st.plotly_chart(fig_profile, use_container_width=True)

        st.caption(
            "This profile compares the average behaviour of each category across the main calculated indicators. "
            "Higher values always represent more favourable conditions."
        )

    st.markdown("### Selected neighbourhood profile")

    detail_neighbourhood = st.selectbox(
        "Select neighbourhood",
        sorted(gdf_filtered["nombre"].dropna().unique())
    )

    row = gdf_filtered[gdf_filtered["nombre"] == detail_neighbourhood].iloc[0]

    min_noise = gdf_filtered["nivel_ruido_medio"].min()
    max_noise = gdf_filtered["nivel_ruido_medio"].max()

    if max_noise != min_noise:
        low_noise_score = 100 - ((row["nivel_ruido_medio"] - min_noise) / (max_noise - min_noise) * 100)
    else:
        low_noise_score = 50

    vulnerability_radar = row["vulnerability_score"] if pd.notna(row["vulnerability_score"]) else 0

    radar_labels = ["Acoustic quality", "Low noise", "Low vulnerability", "Green areas", "Dynamic index"]
    radar_values = [
        row["sleep_score_medio"],
        low_noise_score,
        vulnerability_radar,
        row["porcentaje_zona_verde"],
        row["dynamic_index"]
    ]

    fig_radar = go.Figure()

    fig_radar.add_trace(go.Scatterpolar(
        r=radar_values + [radar_values[0]],
        theta=radar_labels + [radar_labels[0]],
        fill="toself",
        name=detail_neighbourhood,
        line_color="#dc2626"
    ))

    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100])
        ),
        title=f"Profile of {detail_neighbourhood}",
        showlegend=False,
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(color="#1f2937")
    )

    st.plotly_chart(fig_radar, use_container_width=True)

    st.caption(
        "The radar chart summarises the selected neighbourhood. Values closer to 100 represent more favourable conditions."
    )

    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("Dynamic index", row["dynamic_index"])
    d2.metric("Acoustic quality", row["sleep_score_medio"])
    d3.metric("Noise level", row["nivel_ruido_medio"])
    d4.metric("Green area (%)", row["porcentaje_zona_verde"])
    d5.metric("High/extreme noise (%)", row["porcentaje_ruido_alto_extremo"])