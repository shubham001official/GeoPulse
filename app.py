import streamlit as st
from supabase import create_client
import pandas as pd
import geopandas as gpd
from shapely import wkb
from shapely.geometry import shape
import pydeck as pdk
from streamlit_image_comparison import image_comparison
import plotly.express as px

# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="GeoPulse | Urban Intelligence",
    layout="wide",
)

st.title("🌍 GeoPulse: Pune Urban Expansion (2019–2025)")
st.markdown(
    "Visualizing AI-detected urban expansion hotspots from Sentinel-2 satellite data."
)

# ============================================================
# 2. LOAD DATA FROM SUPABASE
# ============================================================


@st.cache_data(ttl=3600)
def load_data():
    """Load urban hotspot data from Supabase and prepare map coordinates."""
    supabase = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )

    response = supabase.table("urban_hotspots").select("*").limit(5000).execute()
    data = response.data

    if not data:
        return gpd.GeoDataFrame()

    df = pd.DataFrame(data)

    def parse_geometry(value):
        if isinstance(value, dict):
            return shape(value)
        return wkb.loads(bytes.fromhex(value))

    df["geometry"] = df["geom"].apply(parse_geometry)

    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    # Calculate centroids safely by projecting to meters (EPSG:3857) first
    gdf_projected = gdf.to_crs("EPSG:3857")
    gdf["lon"] = gdf_projected.geometry.centroid.to_crs("EPSG:4326").x
    gdf["lat"] = gdf_projected.geometry.centroid.to_crs("EPSG:4326").y

    return gdf


with st.spinner("Fetching spatial data from Supabase..."):
    hotspots_gdf = load_data()

# ============================================================
# 3. DASHBOARD NAVIGATION (TABS)
# ============================================================

# Create tabs for the different pages of our application
tab1, tab2, tab3 = st.tabs(
    ["📍 Interactive Change Map", "⏳ Time Machine (2019 vs 2025)", "City Analytics"]
)

# ------------------------------------------------------------
# TAB 1: THE CHANGE MAP
# ------------------------------------------------------------
with tab1:
    if hotspots_gdf.empty:
        st.warning(
            "No data found in the database. Please check your Supabase connection."
        )
    else:
        total_area = hotspots_gdf["area_hectares"].sum()
        total_hotspots = len(hotspots_gdf)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Hotspots Mapped", f"{total_hotspots:,}")
        col2.metric("Total Area Urbanized", f"{total_area:,.2f} Hectares")
        col3.metric("Primary Transition", "Vegetation → Built-up")

        st.subheader("Interactive Hotspot Map")
        st.caption(
            "Each circle represents an urban expansion hotspot. Circle size indicates hotspot area."
        )

        map_columns = ["lon", "lat", "area_hectares", "change_type"]
        map_df = hotspots_gdf[map_columns].copy()

        # Logarithmic radius scaling
        map_df["radius"] = (map_df["area_hectares"].clip(lower=0.01) + 1).apply(
            lambda x: min(500, 80 * x**0.5)
        )

        hotspot_layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[lon, lat]",
            get_radius="radius",
            get_fill_color=[220, 50, 50, 110],
            get_line_color=[180, 20, 20, 180],
            get_line_width=1,
            pickable=True,
            stroked=True,
            parameters={"depthTest": False},
        )

        view_state = pdk.ViewState(
            latitude=18.5204,
            longitude=73.8567,
            zoom=10.5,
            pitch=0,
            bearing=0,
        )

        tooltip = {
            "html": """
                <div style="padding: 8px;">
                    <b>Urban Hotspot</b><br/>
                    <b>Area:</b> {area_hectares} hectares<br/>
                    <b>Transition:</b> {change_type}
                </div>
            """,
            "style": {
                "backgroundColor": "rgba(20, 20, 20, 0.9)",
                "color": "white",
                "fontSize": "13px",
                "padding": "8px",
                "borderRadius": "6px",
            },
        }

        deck = pdk.Deck(
            layers=[hotspot_layer],
            initial_view_state=view_state,
            map_style="light",
            tooltip=tooltip,
        )

        st.pydeck_chart(deck, width="stretch")

# ------------------------------------------------------------
# TAB 2: THE TIME MACHINE
# ------------------------------------------------------------
with tab2:
    st.subheader("⏳ Satellite Time Machine")
    st.markdown(
        "Drag the slider to visually compare the landscape transition over a 6-year period."
    )

    st.info(
        "💡 **Observation:** Focus on the North-East corridor (Wagholi/Kharadi) and Hinjawadi. Watch how the vegetation is replaced by concrete grid patterns."
    )

    # NESTED TABS: This prevents the app from reloading when switching views!
    view_tab1, view_tab2 = st.tabs(
        ["🌍 True Color (Real World)", "🔴 Urban Sprawl Highlight"]
    )

    with view_tab1:
        image_comparison(
            img1="screenshots/pune_2019.jpg",
            img2="screenshots/pune_2025.jpg",
            label1="2019 (Nature)",
            label2="2025 (Concrete)",
            starting_position=50,
            show_labels=True,
            make_responsive=True,
            in_memory=True,
        )

    with view_tab2:
        st.caption(
            "🔴 **Red/Orange:** Urban/Concrete/Barren | 🟢 **Green:** Vegetation"
        )
        image_comparison(
            img1="screenshots/pune_2019_sprawl.jpg",
            img2="screenshots/pune_2025_sprawl.jpg",
            label1="2019",
            label2="2025",
            starting_position=50,
            show_labels=True,
            make_responsive=True,
            in_memory=True,
        )


# ------------------------------------------------------------
# TAB 3: CITY ANALYTICS
# ------------------------------------------------------------
with tab3:
    st.subheader("📊 Urban Expansion Analytics")
    st.markdown(
        "Macro-level insights into how Pune's metropolitan footprint is scaling."
    )

    if not hotspots_gdf.empty:
        analytics_df = hotspots_gdf.copy()

        # 1. Categorize Hotspots by Size
        # Micro (<1 ha), Small (1-5 ha), Medium (5-20 ha), Mega (>20 ha)
        bins = [0, 1, 5, 20, float("inf")]
        labels = [
            "Micro (< 1 ha)",
            "Small (1 - 5 ha)",
            "Medium (5 - 20 ha)",
            "Mega (> 20 ha)",
        ]
        analytics_df["Scale"] = pd.cut(
            analytics_df["area_hectares"], bins=bins, labels=labels
        )

        # Create two side-by-side columns for our charts
        col1, col2 = st.columns(2)

        with col1:
            # Chart A: Distribution of Sprawl
            scale_counts = analytics_df["Scale"].value_counts().reset_index()
            scale_counts.columns = ["Scale Category", "Number of Hotspots"]

            # Sort categorically so it displays in order of size
            scale_counts["Scale Category"] = pd.Categorical(
                scale_counts["Scale Category"], categories=labels, ordered=True
            )
            scale_counts = scale_counts.sort_values("Scale Category")

            fig1 = px.bar(
                scale_counts,
                x="Scale Category",
                y="Number of Hotspots",
                title="Sprawl Distribution by Scale",
                text_auto=True,
                color="Scale Category",
                color_discrete_sequence=[
                    "#ffbaba",
                    "#ff7b7b",
                    "#ff5252",
                    "#a70000",
                ],  # Gradient of reds
            )
            fig1.update_traces(textposition="outside")
            fig1.update_layout(showlegend=False, height=450)
            st.plotly_chart(fig1, width='stretch')

        with col2:
            # Chart B: Top 10 Largest Developments
            top_10 = analytics_df.nlargest(10, "area_hectares").copy()
            top_10 = top_10.sort_values(
                "area_hectares", ascending=True
            )  # Sort ascending for Plotly horizontal bars

            # Create a clean label for the Y-axis based on size rank
            top_10["Development Zone"] = [f"Zone {10-i}" for i in range(len(top_10))]

            fig2 = px.bar(
                top_10,
                x="area_hectares",
                y="Development Zone",
                orientation="h",
                title="Top 10 Largest Continuous Expansions",
                text="area_hectares",
                color="area_hectares",
                color_continuous_scale="Reds",
            )
            fig2.update_traces(texttemplate="%{text:.2f} ha", textposition="inside")
            fig2.update_layout(coloraxis_showscale=False, height=450)
            st.plotly_chart(fig2, width="stretch")

    else:
        st.info("No spatial data available to generate analytics.")
