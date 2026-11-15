import json
import io
import math
from datetime import date, timedelta

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

# ------------------------------------------------------------
# DELTA WATCH | Interactive scientific mapping prototype
# Supports GeoJSON and CSV point datasets in this version.
# GeoTIFF raster support will be added in the next development step.
# ------------------------------------------------------------

st.set_page_config(
    page_title="DELTA WATCH | Nile Delta",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- STYLE ----------
st.markdown(
    """
    <style>
    .stApp { background: #0b1420; color: #e8f0f5; }
    section[data-testid="stSidebar"] { background: #111f2e; }
    h1, h2, h3 { color: #e8f0f5; }
    [data-testid="stMetric"] {
        background: #142638;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #263d50;
    }
    [data-testid="stMetricValue"] { color: #56d6c2; }
    .dw-note {
        padding: 12px 15px;
        border: 1px solid #31516a;
        border-radius: 10px;
        background: #102337;
        margin: 8px 0 16px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- PILOT REGION ----------
PLACES = {
    "Port Said": (31.2653, 32.3019),
    "Damietta": (31.4175, 31.8144),
    "Lake Manzala": (31.20, 32.00),
    "Baltim": (31.56, 31.08),
}

CENTER = (31.35, 31.75)

# ---------- RESOURCE LIBRARY ----------
RESOURCES = {
    "NASA Earthdata Search": (
        "Discover and access NASA Earth science datasets",
        "https://search.earthdata.nasa.gov/search",
        "NASA",
    ),
    "ASF Data Search Vertex": (
        "Search and access SAR satellite data",
        "https://search.asf.alaska.edu/",
        "NASA / ASF",
    ),
    "ASF Search API Manual": (
        "Documentation for querying the Alaska Satellite Facility SAR archive",
        "https://docs.asf.alaska.edu/api/basics/",
        "NASA / ASF",
    ),
    "Finding NISAR Data with ASF Search": (
        "Official examples for searching NISAR products and data-maturity classes",
        "https://hyp3-docs.asf.alaska.edu/nisar-docs/asf-search/",
        "NASA / ASF",
    ),
    "NISAR Data User Guide": (
        "Guidance for accessing and understanding NISAR data",
        "https://nisar-docs.asf.alaska.edu/",
        "NASA / ASF",
    ),
    "Introduction to Remote Sensing": (
        "Learn remote sensing fundamentals",
        "https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/remote-sensing",
        "NASA",
    ),
    "Introduction to SAR": (
        "Understand radar imaging, wavelength and scattering",
        "https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar",
        "NASA",
    ),
    "NASA ARSET Trainings": (
        "Remote sensing and applied science training",
        "https://appliedsciences.nasa.gov/get-involved/training",
        "NASA",
    ),
    "NISAR StoryMaps": (
        "Explore examples of SAR applications",
        "https://nisar.jpl.nasa.gov/applications/arcgis-storymaps/",
        "NASA",
    ),
    "NISAR Applications White Papers": (
        "Explore societal applications of NISAR",
        "https://nisar.jpl.nasa.gov/applications/societal-benefit/",
        "NASA",
    ),
    "UAVSAR Postcards": (
        "Visual examples of airborne SAR observations",
        "https://uavsar.jpl.nasa.gov/education/postcards.html",
        "NASA",
    ),
    "RADARSAT Constellation Mission": (
        "Canadian SAR mission data",
        "https://donnees-data.asc-csa.gc.ca/en/dataset/rcm",
        "Partner agency",
    ),
    "Canadian SAR Python Tutorial": (
        "Practical SAR processing tutorial",
        "https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial",
        "Partner agency",
    ),
    "RADARSAT-1 Data": (
        "Open RADARSAT-1 archive information",
        "https://donnees-data.asc-csa.gc.ca/en/dataset/radarsat1",
        "Partner agency",
    ),
    "SAOCOM Catalogue": (
        "Argentinian SAR data catalogue",
        "https://catalogos.conae.gov.ar/catalogo/catalogoSatSaocomInfo.html",
        "Partner agency",
    ),
    "SAOCOM Registration": (
        "Information about SAOCOM catalogue access",
        "https://www.argentina.gob.ar/noticias/la-informacion-saocom-cada-vez-mas-accesible",
        "Partner agency",
    ),
}


# ---------- MAP HELPERS ----------
def add_pilot_markers(map_object, selected_places=None):
    selected_places = selected_places or list(PLACES.keys())
    for name in selected_places:
        lat, lon = PLACES[name]
        folium.Marker(
            location=[lat, lon],
            tooltip=name,
            popup=f"<b>{name}</b><br>Approximate pilot-area reference point",
            icon=folium.Icon(color="cadetblue", icon="info-sign"),
        ).add_to(map_object)


def make_base_map(selected_places=None):
    m = folium.Map(
        location=CENTER,
        zoom_start=8,
        tiles=None,
        control_scale=True,
    )
    folium.TileLayer(
        tiles="OpenStreetMap",
        name="Street map",
        control=True,
    ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles © Esri",
        name="Satellite imagery",
        overlay=False,
        control=True,
    ).add_to(m)
    add_pilot_markers(m, selected_places)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


def numeric_column_options(frame):
    return [
        column
        for column in frame.columns
        if pd.api.types.is_numeric_dtype(frame[column])
    ]


def validate_csv_points(frame):
    lower_to_original = {str(c).strip().lower(): c for c in frame.columns}
    lat_name = next(
        (lower_to_original[k] for k in ["latitude", "lat", "y"] if k in lower_to_original),
        None,
    )
    lon_name = next(
        (lower_to_original[k] for k in ["longitude", "lon", "lng", "long", "x"] if k in lower_to_original),
        None,
    )
    if lat_name is None or lon_name is None:
        raise ValueError(
            "CSV needs coordinate columns named latitude/longitude, lat/lon, or y/x."
        )

    clean = frame.copy()
    clean["_latitude"] = pd.to_numeric(clean[lat_name], errors="coerce")
    clean["_longitude"] = pd.to_numeric(clean[lon_name], errors="coerce")
    clean = clean.dropna(subset=["_latitude", "_longitude"])

    clean = clean[
        clean["_latitude"].between(-90, 90)
        & clean["_longitude"].between(-180, 180)
    ]
    if clean.empty:
        raise ValueError("No valid latitude/longitude rows were found.")
    return clean


def add_csv_points(map_object, frame, value_column=None):
    if value_column and value_column in frame.columns:
        values = pd.to_numeric(frame[value_column], errors="coerce")
        valid_values = values.dropna()
        if not valid_values.empty:
            low, high = float(valid_values.min()), float(valid_values.max())
        else:
            low, high = 0.0, 1.0
    else:
        values = pd.Series([None] * len(frame), index=frame.index)
        low, high = 0.0, 1.0

    for idx, row in frame.iterrows():
        value = values.loc[idx]
        if pd.notna(value) and value_column:
            if high == low:
                color = "#f4d35e"
            else:
                fraction = (float(value) - low) / (high - low)
                # Simple blue-to-red ramp for visual inspection, not a scientific classification.
                red = int(40 + 215 * fraction)
                blue = int(220 - 180 * fraction)
                color = f"#{red:02x}65{blue:02x}"
            popup_value = f"<br>{value_column}: {float(value):g}"
        else:
            color = "#56d6c2"
            popup_value = ""

        folium.CircleMarker(
            location=[row["_latitude"], row["_longitude"]],
            radius=5,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            popup=f"CSV record {idx + 1}{popup_value}",
        ).add_to(map_object)


def add_geojson(map_object, geojson_object):
    folium.GeoJson(
        geojson_object,
        name="Uploaded GeoJSON",
        style_function=lambda feature: {
            "color": "#56d6c2",
            "weight": 2,
            "fillColor": "#56d6c2",
            "fillOpacity": 0.18,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=list(
                (geojson_object.get("features") or [{}])[0].get("properties", {}).keys()
            )[:3]
        ) if (geojson_object.get("features") or [{}])[0].get("properties") else None,
    ).add_to(map_object)


# ---------- LIVE ASF ARCHIVE SEARCH ----------
NISAR_L2_PRODUCTS = ["GSLC", "GUNW", "GCOV", "GOFF"]

# Search windows are intentionally approximate rectangles around named pilot areas.
# They are catalogue query windows, not official administrative or coastline boundaries.
SEARCH_AREAS = {
    "Entire pilot region": (30.95, 30.90, 32.55, 31.80),  # west, south, east, north
    "Port Said area": (32.15, 31.15, 32.47, 31.42),
    "Damietta area": (31.65, 31.27, 32.00, 31.56),
    "Lake Manzala area": (31.75, 31.05, 32.20, 31.36),
    "Baltim area": (30.88, 31.43, 31.28, 31.69),
}


def area_to_wkt(bounds):
    """Convert west/south/east/north bounds to a closed WKT polygon."""
    west, south, east, north = bounds
    return (
        "POLYGON(("
        f"{west} {south}, {east} {south}, {east} {north}, "
        f"{west} {north}, {west} {south}"
        "))"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def search_asf_catalog(mission, product_levels, area_wkt, start_iso, end_iso, maturity, max_results):
    """Search ASF metadata using its supported asf_search Python client.

    This returns catalogue metadata and footprints only. It does not download or
    process the underlying SAR measurements.
    """
    import asf_search as asf

    options = {
        "dataset": ["NISAR"] if mission == "NISAR" else ["SENTINEL-1"],
        "intersectsWith": area_wkt,
        "start": start_iso,
        "end": end_iso,
        "maxResults": int(max_results),
    }
    if product_levels:
        options["processingLevel"] = list(product_levels)
    if mission == "NISAR" and maturity and maturity != "Any maturity":
        options["dataMaturity"] = maturity

    search_options = asf.ASFSearchOptions(**options)
    results = asf.search(opts=search_options)
    if hasattr(results, "geojson"):
        feature_collection = results.geojson()
    elif isinstance(results, dict):
        feature_collection = results
    else:
        raise RuntimeError("ASF returned an unrecognized results object.")

    if isinstance(feature_collection, str):
        feature_collection = json.loads(feature_collection)
    if not isinstance(feature_collection, dict):
        raise RuntimeError("ASF returned an unexpected GeoJSON response.")
    if feature_collection.get("type") != "FeatureCollection":
        # Some clients may wrap features differently; fail clearly rather than
        # trying to interpret an unknown payload as product records.
        raise RuntimeError("ASF response did not contain a GeoJSON FeatureCollection.")
    return feature_collection


def first_property(properties, names, default=""):
    """Get the first non-empty metadata value among common ASF field aliases."""
    for name in names:
        value = properties.get(name)
        if value not in (None, ""):
            if isinstance(value, (list, tuple)):
                return ", ".join(str(item) for item in value)
            return str(value)
    return default


def format_catalog_time(value):
    if not value:
        return "Not provided"
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def normalize_asf_features(feature_collection):
    """Convert ASF features into display rows while preserving their source values."""
    rows = []
    for feature in feature_collection.get("features", []):
        properties = feature.get("properties") or {}
        product_id = first_property(
            properties,
            ["fileID", "sceneName", "fileName", "product_file_id", "productId", "granuleUR", "title"],
            default="Product ID not supplied",
        )
        acquisition = first_property(
            properties,
            ["startTime", "acquisitionDate", "sceneDate", "start", "acquisition_time", "time_start"],
        )
        product_type = first_property(
            properties,
            ["processingLevel", "productType", "shortName", "product_type"],
            default="Not provided",
        )
        platform = first_property(
            properties,
            ["platform", "mission", "dataset", "platformName"],
            default="Not provided",
        )
        maturity = first_property(
            properties,
            ["dataMaturity", "data_maturity", "maturity", "qualityLevel"],
            default="Not provided by catalogue response",
        )
        product_url = first_property(
            properties,
            ["url", "downloadUrl", "productUrl", "dataLink", "product_url", "dataUrl"],
        )
        browse_url = first_property(
            properties,
            ["browse", "browseUrl", "thumbnail", "browseURL"],
        )
        rows.append(
            {
                "Product ID": product_id,
                "Acquisition (UTC)": format_catalog_time(acquisition),
                "Product type": product_type,
                "Mission / platform": platform,
                "Data maturity": maturity,
                "Product link": product_url,
                "Preview link": browse_url,
            }
        )
    return rows


def add_asf_footprints(map_object, feature_collection):
    """Add actual ASF-returned geometries to a Folium map when supplied."""
    valid_features = [
        feature
        for feature in feature_collection.get("features", [])
        if isinstance(feature, dict) and feature.get("geometry")
    ]
    if valid_features:
        folium.GeoJson(
            {"type": "FeatureCollection", "features": valid_features},
            name="ASF catalogue footprints",
            style_function=lambda feature: {
                "color": "#f4c95d",
                "weight": 2,
                "fillColor": "#f4c95d",
                "fillOpacity": 0.10,
            },
            highlight_function=lambda feature: {"weight": 4, "fillOpacity": 0.22},
        ).add_to(map_object)
    return len(valid_features)


# ---------- SIDEBAR ----------
st.sidebar.markdown("# 🌍 DELTA WATCH")
st.sidebar.caption("NILE DELTA GEOSPATIAL MONITOR")
st.sidebar.divider()

page = st.sidebar.radio(
    "EXPLORE",
    [
        "Overview",
        "Interactive Map",
        "Satellite Data Search",
        "Land Subsidence",
        "Coastal Change",
        "Flood Monitoring",
        "Soil Conditions",
        "Data & Resources",
        "Methodology",
        "User Guide",
        "Future Plans",
    ],
)

st.sidebar.divider()
st.sidebar.markdown("**Pilot Region**")
st.sidebar.write("Northeastern Nile Delta, Egypt")
st.sidebar.caption("Port Said • Damietta • Lake Manzala • Baltim")
st.sidebar.info("Live ASF catalogue search for NISAR and Sentinel-1, plus manual CSV point and GeoJSON uploads. Raw SAR processing and GeoTIFF analysis are not included.")

# ---------- HEADER ----------
PAGE_SUBTITLES = {
    "Overview": "Explore environmental change across the northeastern Nile Delta.",
    "Interactive Map": "Explore pilot locations and overlay your own geospatial datasets.",
    "Satellite Data Search": "Discover real NISAR and Sentinel-1 archive records intersecting the pilot region.",
    "Land Subsidence": "Inspect uploaded, already-processed ground-deformation measurements.",
    "Coastal Change": "Explore coastal observations and the evidence needed for shoreline comparison.",
    "Flood Monitoring": "Explore SAR-based flood mapping concepts and suitable evidence.",
    "Soil Conditions": "Explore soil and surface-condition observations with appropriate caveats.",
    "Data & Resources": "Official data portals, mission guides and learning materials.",
    "Methodology": "How the prototype discovers, documents and interprets satellite data.",
    "User Guide": "A step-by-step guide to every page, control and scientific term in DELTA WATCH.",
    "Future Plans": "The planned development roadmap: what exists today and what comes next.",
}
if page == "Overview":
    st.title("DELTA WATCH")
    st.markdown("### " + PAGE_SUBTITLES[page])
    st.caption("A geospatial research prototype | NASA Space Apps Challenge 2026")
else:
    display_title = "Data & Learning Resource Library" if page == "Data & Resources" else page
    st.title(display_title)
    st.caption(PAGE_SUBTITLES.get(page, "DELTA WATCH | NASA Space Apps Challenge 2026"))

st.markdown(
    '<div class="dw-note"><b>Data integrity notice:</b> Pilot markers and search windows are approximate. '
    'Satellite catalogue records are acquisition metadata and footprints, not environmental measurements. '
    'This prototype does not derive subsidence, shoreline change, flood extent or soil moisture from raw SAR. '
    'Uploaded values are displayed as supplied and are not independently validated.</div>',
    unsafe_allow_html=True,
)

# ---------- OVERVIEW ----------
if page == "Overview":
    st.subheader("Regional Intelligence Overview")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pilot locations", "4")
    col2.metric("Monitoring themes", "4")
    col3.metric("Primary mission of interest", "NISAR")
    col4.metric("Data connection", "Manual upload")

    left, right = st.columns([1.45, 1])
    with left:
        st.subheader("Northeastern Nile Delta")
        overview_map = make_base_map()
        st_folium(overview_map, height=470, width=None, key="overview_map")
        st.caption("Approximate pilot-area markers. Choose the satellite imagery basemap using the layer control.")
    with right:
        st.subheader("Research themes")
        st.markdown(
            """
            **01 — Land subsidence**  
            Ground deformation and surface movement.

            **02 — Coastal change**  
            Shoreline dynamics and coastal erosion.

            **03 — Flood monitoring**  
            Mapping water extent using radar observations.

            **04 — Soil conditions**  
            Exploring appropriate soil and surface-condition datasets.
            """
        )
        st.subheader("Why the Nile Delta?")
        st.write(
            "The Nile Delta supports major population centers, agriculture, wetlands "
            "and infrastructure. Geospatial monitoring can help researchers investigate "
            "environmental change and support evidence-based planning."
        )

# ---------- INTERACTIVE MAP ----------
elif page == "Interactive Map":
    st.subheader("Interactive Geospatial Map")
    st.write("Explore the pilot region and add your own geographic datasets.")

    selected = st.multiselect(
        "Pilot locations",
        list(PLACES.keys()),
        default=list(PLACES.keys()),
    )
    uploaded = st.file_uploader(
        "Upload a geographic dataset",
        type=["geojson", "json", "csv"],
        help="This build accepts GeoJSON features or CSV point coordinates. GeoTIFF support is coming next.",
        key="general_map_upload",
    )

    map_object = make_base_map(selected)
    uploaded_frame = None
    uploaded_geojson = None
    value_column = None

    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".csv"):
                uploaded_frame = pd.read_csv(uploaded)
                uploaded_frame = validate_csv_points(uploaded_frame)
                candidates = numeric_column_options(uploaded_frame.drop(
                    columns=["_latitude", "_longitude"], errors="ignore"
                ))
                candidates = [
                    c for c in candidates
                    if str(c).strip().lower() not in {
                        "latitude", "longitude", "lat", "lon", "lng", "long", "x", "y"
                    }
                ]
                if candidates:
                    value_column = st.selectbox(
                        "Optional measurement column to visualize",
                        ["Do not color by a measurement"] + candidates,
                        key="map_value_column",
                    )
                    if value_column == "Do not color by a measurement":
                        value_column = None
                add_csv_points(map_object, uploaded_frame, value_column)
                st.success(f"Loaded {len(uploaded_frame)} valid CSV point records.")
            else:
                uploaded_geojson = json.load(uploaded)
                if uploaded_geojson.get("type") not in {
                    "FeatureCollection", "Feature", "GeometryCollection",
                    "Point", "MultiPoint", "LineString", "MultiLineString",
                    "Polygon", "MultiPolygon",
                }:
                    raise ValueError("The uploaded JSON does not appear to be GeoJSON.")
                if uploaded_geojson.get("type") == "FeatureCollection" and not uploaded_geojson.get("features"):
                    raise ValueError("The GeoJSON FeatureCollection contains no features.")
                add_geojson(map_object, uploaded_geojson)
                st.success("GeoJSON loaded onto the map.")
        except Exception as error:
            st.error(f"Could not read this dataset: {error}")

    folium.LayerControl(collapsed=False).add_to(map_object)
    map_result = st_folium(
        map_object,
        height=620,
        width=None,
        key="main_interactive_map",
        returned_objects=["last_clicked", "last_object_clicked"],
    )

    clicked = (map_result or {}).get("last_clicked")
    if clicked:
        st.subheader("Selected map coordinate")
        st.write(
            f"Latitude: `{clicked['lat']:.6f}`  |  Longitude: `{clicked['lng']:.6f}`"
        )
        st.caption("This is a map click coordinate, not a measured subsidence value.")

    st.caption(
        "Map tiles require an internet connection. Uploaded CSV coordinates are assumed to be "
        "geographic latitude/longitude in WGS84 (EPSG:4326). Reproject other coordinate systems before upload."
    )

# ---------- LAND SUBSIDENCE ----------
elif page == "Land Subsidence":
    st.subheader("Land Subsidence Explorer")
    st.write(
        "Upload an already-processed deformation dataset to inspect its spatial distribution. "
        "This prototype does not process raw SAR scenes into InSAR deformation products."
    )

    st.markdown("#### Upload a measurement point dataset")
    st.caption(
        "For this first upload workflow, use CSV with latitude and longitude columns, "
        "plus an optional numeric displacement column."
    )
    sub_file = st.file_uploader(
        "Choose a CSV file",
        type=["csv"],
        key="subsidence_csv",
    )

    if sub_file is not None:
        try:
            data = validate_csv_points(pd.read_csv(sub_file))
            numeric = numeric_column_options(
                data.drop(columns=["_latitude", "_longitude"], errors="ignore")
            )
            numeric = [
                c for c in numeric
                if str(c).strip().lower() not in {
                    "latitude", "longitude", "lat", "lon", "lng", "long", "x", "y"
                }
            ]
            if not numeric:
                st.warning("The CSV has coordinates but no additional numeric measurement column.")
                selected_value = None
            else:
                selected_value = st.selectbox(
                    "Choose the displacement measurement column",
                    numeric,
                    key="subsidence_value_column",
                )

            metadata1, metadata2, metadata3 = st.columns(3)
            metadata1.metric("Valid locations", len(data))
            metadata2.metric("Measurement field", selected_value or "Not selected")
            metadata3.metric("Dataset", sub_file.name)

            if selected_value:
                st.markdown("#### Spatial distribution")
                sub_map = make_base_map()
                add_csv_points(sub_map, data, selected_value)
                st_folium(sub_map, height=560, width=None, key="subsidence_map")

                st.markdown("#### Measurement summary")
                values = pd.to_numeric(data[selected_value], errors="coerce").dropna()
                if not values.empty:
                    a, b, c = st.columns(3)
                    a.metric("Minimum", f"{values.min():.3f}")
                    b.metric("Maximum", f"{values.max():.3f}")
                    c.metric("Mean", f"{values.mean():.3f}")

                    st.caption(
                        "These statistics use the uploaded column exactly as supplied. "
                        "Confirm its units, sign convention, reference frame and observation period before interpretation."
                    )
                    fig = px.histogram(
                        x=values,
                        nbins=30,
                        labels={"x": selected_value, "y": "Number of records"},
                        title="Distribution of uploaded measurements",
                    )
                    fig.update_layout(template="plotly_dark")
                    st.plotly_chart(fig, use_container_width=True)

                    with st.expander("Preview uploaded records"):
                        st.dataframe(data, use_container_width=True)
                else:
                    st.warning("No valid numeric values were found in the selected measurement column.")
        except Exception as error:
            st.error(f"Could not process this CSV: {error}")
    else:
        st.info(
            "No dataset uploaded yet. The map will show pilot locations only; "
            "it will not display invented deformation measurements."
        )

    st.markdown("#### What makes a suitable subsidence dataset?")
    st.markdown(
        """
        - Georeferenced displacement measurements or an already-processed deformation raster.
        - A clearly documented unit (for example, mm or cm).
        - Acquisition dates or a defined observation interval.
        - A documented sign convention and reference frame.
        - Processing and quality information, including coherence or uncertainty where available.
        """
    )
    st.warning(
        "A single displacement map is not automatically a subsidence-rate map. "
        "Do not interpret values as mm/year unless the source product defines them as a rate."
    )

# ---------- SATELLITE DATA SEARCH ----------
elif page == "Satellite Data Search":
    st.subheader("Search the ASF SAR archive")
    st.write(
        "Query the Alaska Satellite Facility catalogue for records whose footprints "
        "intersect an approximate Nile Delta study window. Searches return catalogue "
        "metadata; downloading data may require a free NASA Earthdata Login."
    )

    with st.form("asf_search_form"):
        filter1, filter2 = st.columns(2)
        with filter1:
            mission = st.selectbox("Mission", ["NISAR", "Sentinel-1"])
            area_name = st.selectbox("Search area", list(SEARCH_AREAS.keys()))
            max_results = st.selectbox("Maximum records", [25, 50, 100], index=1)
        with filter2:
            today = date.today()
            default_start = today - timedelta(days=365)
            date_range = st.date_input(
                "Acquisition date range (UTC)",
                value=(default_start, today),
                max_value=today,
            )
            if mission == "NISAR":
                product_choice = st.selectbox(
                    "NISAR product type",
                    ["All four L2 products", "GSLC", "GUNW", "GCOV", "GOFF"],
                    help="GSLC: geocoded single-look complex; GUNW: geocoded unwrapped interferogram; GCOV: geocoded covariance; GOFF: geocoded pixel offsets.",
                )
                maturity_choice = st.selectbox(
                    "NISAR data maturity",
                    ["Any maturity", "VALIDATED", "PROVISIONAL", "BETA"],
                    help="VALIDATED: calibrated and validated; PROVISIONAL: calibrated but not fully validated; BETA: pre-calibration. Availability depends on the archive response.",
                )
            else:
                sentinel_products = {
                    "GRD-HD (high resolution)": ["GRD_HD"],
                    "GRD-MD (medium resolution)": ["GRD_MD"],
                    "SLC (complex data for InSAR workflows)": ["SLC"],
                    "All Sentinel-1 product types": [],
                }
                product_choice = st.selectbox(
                    "Sentinel-1 product type",
                    list(sentinel_products.keys()),
                    help="GRD products are commonly used for backscatter and water-extent workflows; SLC is the complex product used in InSAR workflows.",
                )
                maturity_choice = "Any maturity"

        submitted = st.form_submit_button("Search live archive", type="primary", use_container_width=True)

    if submitted:
        # Remove previous results before attempting a new query, so a failed query
        # can never leave stale catalogue records visible as though they were current.
        st.session_state.pop("delta_watch_asf_catalog", None)
        st.session_state.pop("delta_watch_asf_rows", None)
        st.session_state.pop("delta_watch_asf_query", None)
        if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
            st.error("Please select both a start date and an end date.")
        else:
            start_date, end_date = date_range
            if start_date > end_date:
                st.error("The start date must be on or before the end date.")
            else:
                if mission == "NISAR":
                    levels = NISAR_L2_PRODUCTS if product_choice == "All four L2 products" else [product_choice]
                    maturity = maturity_choice
                else:
                    levels = sentinel_products[product_choice]
                    maturity = "Any maturity"

                query_wkt = area_to_wkt(SEARCH_AREAS[area_name])
                start_iso = f"{start_date.isoformat()}T00:00:00Z"
                end_iso = f"{end_date.isoformat()}T23:59:59Z"

                try:
                    with st.spinner("Querying the ASF catalogue..."):
                        catalog = search_asf_catalog(
                            mission,
                            levels,
                            query_wkt,
                            start_iso,
                            end_iso,
                            maturity,
                            max_results,
                        )
                    features = catalog.get("features", [])
                    result_rows = normalize_asf_features(catalog)
                    st.session_state["delta_watch_asf_catalog"] = catalog
                    st.session_state["delta_watch_asf_rows"] = result_rows
                    st.session_state["delta_watch_asf_query"] = {
                        "mission": mission,
                        "area": area_name,
                        "start": start_iso,
                        "end": end_iso,
                        "product": product_choice,
                        "maturity": maturity,
                    }
                    st.success(f"ASF returned {len(features)} catalogue record(s) for this query.")
                except ImportError:
                    st.error(
                        "The ASF search package is not installed. In Command Prompt, run "
                        "`python -m pip install -r requirements.txt`, then restart the app."
                    )
                except Exception as error:
                    st.error(f"The ASF catalogue search could not be completed: {error}")
                    st.caption(
                        "Check your internet connection and try again. You can also open the "
                        "official ASF Search portal directly: https://search.asf.alaska.edu/"
                    )

    catalog = st.session_state.get("delta_watch_asf_catalog")
    result_rows = st.session_state.get("delta_watch_asf_rows")
    query_details = st.session_state.get("delta_watch_asf_query")

    if catalog is not None and result_rows is not None:
        st.divider()
        st.subheader("Catalogue results")
        st.caption(
            f"Last query: {query_details['mission']} | {query_details['area']} | "
            f"{query_details['start'][:10]} to {query_details['end'][:10]} | "
            f"Product selection: {query_details['product']}"
        )
        if result_rows:
            total = len(result_rows)
            geometries = sum(1 for feature in catalog.get("features", []) if feature.get("geometry"))
            metric1, metric2, metric3 = st.columns(3)
            metric1.metric("Records returned", total)
            metric2.metric("Records with footprint geometry", geometries)
            metric3.metric("Mission", query_details["mission"])

            results_df = pd.DataFrame(result_rows)
            st.dataframe(
                results_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Product link": st.column_config.LinkColumn(
                        "Product link",
                        display_text="Open product",
                        help="Direct product links may require NASA Earthdata Login and data-access permissions.",
                    ),
                    "Preview link": st.column_config.LinkColumn(
                        "Preview",
                        display_text="Open preview",
                    ),
                },
            )
            csv_bytes = results_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download result metadata (CSV)",
                data=csv_bytes,
                file_name="delta_watch_asf_catalogue_results.csv",
                mime="text/csv",
            )

            st.markdown("#### Product footprints")
            footprint_map = make_base_map()
            footprint_count = add_asf_footprints(footprint_map, catalog)
            st_folium(
                footprint_map,
                height=520,
                width=None,
                key="asf_catalog_footprints_map",
            )
            if footprint_count:
                st.caption(
                    "Outlined shapes are geometries returned by ASF for the records above. "
                    "They show catalogue footprint coverage, not measured environmental change."
                )
            else:
                st.info(
                    "The returned records did not include footprint geometry in this response. "
                    "The table still shows the metadata supplied by ASF."
                )
        else:
            st.info(
                "The ASF catalogue returned no records for the selected mission, product, "
                "dates and approximate search window. This means no matching records were "
                "returned for this query; it does not prove that no satellite observations "
                "exist outside the selected filters. Try a longer date range, another product "
                "type, or the full pilot region."
            )

    with st.expander("How to interpret the search results"):
        st.markdown(
            """
            - **Catalogue record:** evidence that a data product is listed by ASF for the query.
            - **Product footprint:** the spatial geometry supplied with that catalogue record.
            - **Data maturity:** for NISAR, VALIDATED, PROVISIONAL and BETA describe different processing/validation states. If the response does not include a maturity field, it is shown as not provided.
            - **Product link:** may require a free NASA Earthdata Login to access or download the file.
            - **No records returned:** applies only to the current mission, date, product and area filters.

            This app does not download, decode or process the SAR files. It does not calculate
            subsidence rates, shoreline retreat, flood water extent or soil moisture from these
            metadata records.
            """
        )
    st.markdown(
        "**Catalogue source:** [ASF Search API documentation](https://docs.asf.alaska.edu/api/basics/) · "
        "[NISAR search guide](https://hyp3-docs.asf.alaska.edu/nisar-docs/asf-search/)"
    )


# ---------- USER GUIDE ----------
elif page == "User Guide":
    guide_language = st.radio("Guide language / لغة الدليل", ["English", "العربية"], horizontal=True)
    if guide_language == "العربية":
        st.subheader("مرحبًا بك في دليل DELTA WATCH")
        st.write("هذا الدليل يشرح كيفية استخدام الموقع وفهم البيانات. لا تحتاج إلى خبرة في الاستشعار عن بُعد للبدء.")
        with st.expander("1. نظرة عامة — Overview", expanded=True):
            st.markdown("تعرض ملخصًا للمشروع ومنطقة الدراسة ومحاور المراقبة الأربعة. الأرقام التعريفية للمواقع لا تعني وجود قياسات بيئية فعلية.")
        with st.expander("2. الخريطة التفاعلية — Interactive Map"):
            st.markdown("استخدم الخريطة لاستكشاف مواقع بورسعيد ودمياط وبحيرة المنزلة وبلطيم. يمكنك رفع ملف جغرافي بصيغة GeoJSON أو ملف CSV يحتوي على إحداثيات نقاط. إذا لم يكن لديك ملف، اترك أداة الرفع فارغة. رفع الملف لا يعني التحقق العلمي من محتواه.")
        with st.expander("3. البحث عن بيانات الأقمار — Satellite Data Search"):
            st.markdown("اختر المهمة الفضائية، والفترة الزمنية، ومنطقة البحث، ونوع المنتج، ثم اضغط Search live archive. النتائج سجلات فهرسة من أرشيف ASF وليست قياسات للهبوط الأرضي أو الفيضانات. قد يتطلب تنزيل الملفات حساب NASA Earthdata.")
            st.markdown("**Mission:** القمر أو المهمة التي جمعت البيانات. **Acquisition date range:** فترة التقاط البيانات بالتوقيت العالمي UTC. **Search area:** المنطقة الجغرافية المستخدمة للبحث. **Product type:** نوع المنتج المعالج. **Data maturity:** حالة نضج المنتج إذا وفرها الكتالوج. **Footprint:** الشكل الجغرافي الذي يوضح نطاق تغطية المنتج.")
        with st.expander("4. الهبوط الأرضي — Land Subsidence"):
            st.markdown("تعرض هذه الصفحة بيانات تشوه أرضي معالجة يرفعها المستخدم. لا تحسب الصفحة الهبوط تلقائيًا من ملفات NISAR الخام. افحص مصدر البيانات ووحداتها وتواريخها قبل تفسيرها.")
        with st.expander("5. تغير الساحل والفيضانات والتربة"):
            st.markdown("هذه أقسام استكشافية/مخططة. تغير الساحل يحتاج خطوط شاطئ مؤرخة ومتسقة؛ ورسم الفيضانات يحتاج تصنيفًا مائيًا من بيانات SAR مع تحقق؛ ورطوبة التربة تحتاج خوارزمية مناسبة وبيانات مرجعية.")
        with st.expander("6. الموارد والمنهجية"):
            st.markdown("Data & Resources يحتوي روابط لمصادر رسمية. Methodology يشرح مراحل اكتشاف البيانات واختيارها ومعالجتها وعرضها والتحقق منها.")
        with st.expander("قاموس المصطلحات العلمية"):
            st.markdown("""- **SAR:** رادار ذو فتحة اصطناعية، يرسل ويستقبل إشارات رادارية.
- **NISAR:** مهمة رادارية مشتركة بين NASA وISRO.
- **Sentinel-1:** مهمة رادارية أوروبية.
- **InSAR:** قياس التغير باستخدام التداخل بين صور رادارية متعددة.
- **GSLC:** منتج راداري معقد مُسقط جغرافيًا.
- **GUNW:** منتج تداخل راداري غير ملفوف ومُسقط جغرافيًا.
- **GCOV:** منتج مصفوفة التغاير/التشارك الراداري.
- **GOFF:** منتج إزاحات البكسلات.
- **GeoJSON:** صيغة لتبادل البيانات الجغرافية.
- **CSV:** جدول نصي مفصول بفواصل.
- **UTC:** التوقيت العالمي المنسق.""")
        st.warning("تنبيه علمي: ظهور سجل في الكتالوج لا يثبت حدوث هبوط أو تآكل أو فيضان. يجب تنزيل البيانات المناسبة ومعالجتها والتحقق من النتائج قبل إعلان أي قياس.")
    else:
        st.subheader("Welcome to the DELTA WATCH User Guide")
        st.write("This guide explains how to navigate the app and interpret its information. You do not need remote-sensing experience to get started.")
        with st.expander("1. Overview", expanded=True):
            st.markdown("The Overview summarizes the project, pilot region and four monitoring themes. Location markers are reference points, not measured environmental changes.")
        with st.expander("2. Interactive Map"):
            st.markdown("Explore Port Said, Damietta, Lake Manzala and Baltim. You may upload a GeoJSON file or a CSV containing point coordinates. If you do not have a dataset, leave the uploader empty. Uploaded content is displayed as supplied and is not automatically scientifically validated.")
        with st.expander("3. Satellite Data Search"):
            st.markdown("Choose a mission, acquisition date range, search area, product type and (for NISAR) data maturity, then select **Search live archive**. Results are ASF catalogue metadata, not measurements of subsidence, flooding or soil moisture. A free NASA Earthdata Login may be required to download data.")
            st.markdown("**Mission:** satellite mission. **Acquisition date range:** when observations were collected, in UTC. **Search area:** geographic region queried. **Product type:** the kind of processed data product. **Data maturity:** product processing/validation state when supplied by the catalogue. **Footprint:** geographic outline of a product's coverage.")
        with st.expander("4. Land Subsidence"):
            st.markdown("This page visualizes already-processed deformation values supplied by the user. It does not calculate ground motion directly from raw NISAR files. Check the source, units and dates before interpreting uploaded values.")
        with st.expander("5. Coastal Change, Flood Monitoring and Soil Conditions"):
            st.markdown("These are exploratory/planned analysis themes. Coastal change requires dated, consistently defined shorelines; flood mapping requires a SAR-derived water classification and validation; soil-moisture estimation requires an appropriate retrieval method and reference data.")
        with st.expander("6. Data & Resources and Methodology"):
            st.markdown("Data & Resources links to official data portals and learning material. Methodology describes the stages of data discovery, selection, processing, visualization and validation.")
        with st.expander("Scientific glossary"):
            st.markdown("""- **SAR:** Synthetic Aperture Radar, an active microwave imaging system.
- **NISAR:** A joint NASA–ISRO radar mission.
- **Sentinel-1:** A European radar satellite mission.
- **InSAR:** Interferometric SAR, a method that uses phase differences between radar acquisitions to measure surface change.
- **GSLC:** Geocoded Single Look Complex product.
- **GUNW:** Geocoded Unwrapped Interferogram product.
- **GCOV:** Geocoded Covariance Matrix product.
- **GOFF:** Geocoded Pixel Offsets product.
- **GeoJSON:** A format for geographic vector data.
- **CSV:** A tabular text format.
- **UTC:** Coordinated Universal Time.""")
        st.warning("Scientific caution: a catalogue record does not prove subsidence, erosion, flooding or soil-moisture change. Suitable data must be downloaded, processed and validated before reporting measurements.")

# ---------- FUTURE PLANS ----------
elif page == "Future Plans":
    st.subheader("Development roadmap")
    st.write("DELTA WATCH is being developed in stages. The items below are planned improvements, not features claimed to be operational in this prototype.")
    roadmap = [
        ("1. Data access and management", "Add guided Earthdata authentication, reliable product downloads, metadata provenance and a local catalogue of selected acquisitions."),
        ("2. Raster visualization", "Support GeoTIFF layers, map legends, coordinate reference checks and time-aware layer comparison."),
        ("3. Land deformation analysis", "Build a documented InSAR workflow for suitable NISAR/Sentinel-1 acquisitions, including coherence checks, uncertainty and validation."),
        ("4. Coastal change monitoring", "Extract comparable shorelines from dated imagery and calculate shoreline movement with clearly stated methods and uncertainty."),
        ("5. Flood extent mapping", "Develop SAR-based water classification, before/after event comparison and validation against reference observations."),
        ("6. Soil and agricultural monitoring", "Evaluate suitable soil-moisture products and retrieval methods, then compare with field or trusted reference data."),
        ("7. Alerts and reporting", "Add user-defined monitoring areas, change summaries, downloadable reports and carefully qualified alerts."),
    ]
    for heading, detail in roadmap:
        with st.container(border=True):
            st.markdown(f"**{heading}**")
            st.write(detail)
    st.info("Current capabilities: ASF catalogue metadata search, interactive basemaps, and manual CSV/GeoJSON visualization. Planned analysis features are not yet implemented.")
    st.subheader("Long-term vision")
    st.write("A transparent, accessible geospatial decision-support platform that helps researchers, students, public agencies and environmental organizations explore evidence of environmental change across the northeastern Nile Delta.")

# ---------- OTHER MONITORING THEMES ----------
elif page in ["Coastal Change", "Flood Monitoring", "Soil Conditions"]:
    descriptions = {
        "Coastal Change": (
            "Investigate shoreline movement using georeferenced shorelines or dated imagery.",
            "A defensible comparison needs consistent shoreline definitions, dates and spatial reference information.",
        ),
        "Flood Monitoring": (
            "Explore flood extent from suitable SAR-derived water masks or classified raster/vector products.",
            "A flood map needs acquisition timing, a water-detection method and validation or reference information.",
        ),
        "Soil Conditions": (
            "Explore appropriate soil-moisture or surface-condition products.",
            "Radar backscatter is not itself a direct soil-moisture measurement; retrieval requires suitable methods and validation.",
        ),
    }
    description, caveat = descriptions[page]
    st.subheader(page)
    st.write(description)
    st.info("This section is planned. The first functional analysis workflow is Land Subsidence.")
    st.write(caveat)

# ---------- RESOURCES ----------
elif page == "Data & Resources":
    st.write("Official data portals, mission guides and learning materials.")

    category = st.selectbox(
        "Filter resources",
        ["All resources", "NASA resources", "Partner agency resources"],
    )
    for name, (description, url, provider) in RESOURCES.items():
        if category == "NASA resources" and provider == "Partner agency":
            continue
        if category == "Partner agency resources" and provider != "Partner agency":
            continue
        with st.container(border=True):
            st.markdown(f"**{name}**")
            st.caption(provider)
            st.write(description)
            st.markdown(f"[Open official resource ↗]({url})")

    st.caption(
        "External resources are provided for research and educational use. "
        "Follow each provider's data access and usage terms."
    )

# ---------- METHODOLOGY ----------
elif page == "Methodology":
    st.subheader("Scientific Approach")
    st.markdown(
        """
        ### 1. Data discovery
        Search the ASF catalogue by mission, product type, acquisition dates and a defined area of interest. Record product IDs, available footprints, links and NISAR maturity metadata.

        ### 2. Data selection
        Select observations covering the study area and document acquisition dates,
        product types, coordinate systems and processing status.

        ### 3. Processing and analysis
        - **Land deformation:** suitable InSAR processing and quality assessment.
        - **Flood extent:** SAR backscatter-based water detection.
        - **Coastal change:** dated shoreline extraction and comparison.
        - **Soil conditions:** appropriate retrieval methods and validation.

        ### 4. Visualization
        Present georeferenced maps, comparisons and charts with source and date metadata.

        ### 5. Validation
        Compare outputs with suitable reference datasets and document uncertainty.
        """
    )
    st.divider()
    st.subheader("Data integrity and limitations")
    st.write(
        "NISAR is the primary mission of interest. Other SAR missions may provide "
        "complementary observations, but must be labelled by their actual source. "
        "NISAR cannot provide observations from before its acquisition history. "
        "Product coverage and validation status must be checked before analysis."
    )
    st.info(
        "Current build: live ASF catalogue metadata search for NISAR and Sentinel-1, interactive basemaps, and manual CSV/GeoJSON visualization. "
        "SAR file download, raw SAR/InSAR processing, GeoTIFF raster analysis and independent validation are not implemented."
    )

# ---------- FOOTER ----------
st.divider()
st.caption(
    "DELTA WATCH | NASA Space Apps Challenge 2026 | "
    "Geospatial research prototype for the Nile Delta"
)
