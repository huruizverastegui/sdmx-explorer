import streamlit as st
import pandas as pd
import requests
from io import StringIO
import plotly.express as px

st.set_page_config(page_title="UNICEF SDMX API Data Explorer", layout="wide")

st.title("UNICEF SDMX API Data Explorer")

# Load the mapping CSV file (now using the classified version)
# Expected columns include: 'dataflow_name', 'agency', 'dataflow_id', 'geography', 'geography_id',
# 'indicator', 'indicator_id', 'category', and (optionally) 'Country'
try:
    df_mapping = pd.read_csv("mapping_sdmx_2025_03_20_country_category_cleaned.csv")
except Exception as e:
    st.error("Error loading CSV file: " + str(e))
    st.stop()

##############################################
# Step 1: Geography Selection (using Country column)
##############################################
# If you want to use the "Country" column instead of "geography", you can first check if it exists.
all_geographies = sorted(df_mapping["country"].dropna().unique(), key=lambda x: str(x))


selected_geographies = st.multiselect("Select country", all_geographies)
if not selected_geographies:
    st.info("Please select at least one country.")
    st.stop()

# Filter the mapping by the selected geography(ies)
df_geo = df_mapping[df_mapping["country"].isin(selected_geographies)]

##############################################
# Step 1.5: National vs. Subnational Filter
##############################################
# Assuming your mapping dataframe has a column "national" with values 0 (subnational) or 1 (national)
if "national" in df_geo.columns:
    national_option = st.radio("Select data level", options=["National", "Subnational"], index=0)
    # Convert "National" to 1 and "Subnational" to 0.
    level = 1 if national_option == "National" else 0
    df_geo = df_geo[df_geo["national"] == level]

# If subnational is selected, enforce that exactly one country is chosen.
if national_option == "Subnational" and len(selected_geographies) != 1:
    st.error("For subnational data, please select exactly one country.")
    st.stop()

if national_option == "Subnational" and df_geo.empty:
    st.error("No subnational data available for the selected country")
    st.stop()

##############################################
# Step 1.75: Category Filter
##############################################
if "category" in df_geo.columns:
    available_categories = sorted(df_geo["category"].dropna().unique(), key=lambda x: str(x))
    selected_categories = st.multiselect("Select Category", available_categories)
    if selected_categories:
        df_geo = df_geo[df_geo["category"].isin(selected_categories)]

##############################################
# Step 2: Indicator Selection
##############################################
available_indicators = sorted(df_geo["indicator"].dropna().unique(), key=lambda x: str(x))
selected_indicators = st.multiselect("Select Indicator(s)", available_indicators, key="indicator_multiselect")
if not selected_indicators:
    st.info("Please select at least one indicator.")
    st.stop()

# If subnational is selected, enforce that exactly one indicator is chosen.
if national_option == "Subnational" and len(selected_indicators) != 1:
    st.error("For subnational data, please select exactly one indicator.")
    st.stop()

# Enforce limitation: either multiple geographies with one indicator or one geography with multiple indicators.
if len(selected_geographies) > 1 and len(selected_indicators) > 1:
    st.error("Please select either multiple countries with one indicator, or one country with multiple indicators.")
    st.stop()

##############################################
# Step 3: Determine Candidate Data Flows
##############################################
df_candidates = df_geo[df_geo["indicator"].isin(selected_indicators)]
candidate_flows = sorted(df_candidates["dataflow_name"].dropna().unique(), key=lambda x: str(x))
if not candidate_flows:
    st.error("No data flows found for the selected geography, category, and indicator(s).")
    st.stop()

if len(candidate_flows) == 1:
    chosen_dataflows = candidate_flows
    st.info(f"Automatically selected dataflow: {candidate_flows[0]}")
else:
    chosen_dataflows = st.multiselect("Multiple data flows found. Please select the data flows to query", candidate_flows, default=candidate_flows)
    if not chosen_dataflows:
        st.error("Please select at least one data flow to query.")
        st.stop()

##############################################
# Step 4: Fetch Data for Each Selected Dataflow
##############################################


if st.button("Fetch Data"):

    st.subheader("Fetching Data")
    with st.expander("**Details of fetching data**", expanded=False):

        flow_data = {}
        for flow in chosen_dataflows:
            df_flow = df_candidates[df_candidates["dataflow_name"] == flow]
            if df_flow.empty:
                st.error(f"No mapping data found for dataflow: {flow}")
                continue
            first_row = df_flow.iloc[0]
            agency = first_row["agency"]
            dataflow_id = first_row["dataflow_id"]
            # Use the appropriate column based on what was used above


            if national_option == "National":
                geo_ids = df_flow[df_flow["country"].isin(selected_geographies)]["geography_id"].unique().tolist()
                geos = df_flow[df_flow["country"].isin(selected_geographies)]["geography"].unique().tolist()
            
            if national_option == "Subnational":
                geo_ids = ""

            indicator_ids = df_flow[df_flow["indicator"].isin(selected_indicators)]["indicator_id"].unique().tolist()
            geography_id_str = "+".join(geo_ids)
            geography_str = "+".join(geos)
            indicator_id_str = "+".join(indicator_ids)
            
            api_url = (
                f"https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data/"
                f"{agency},{dataflow_id},1.0/{geography_id_str}.{indicator_id_str}"
                "?format=csv&labels=both"
            )

            api_url_bis = (
                f"https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data/"
                f"{agency},{dataflow_id},1.0/.{geography_id_str}..{indicator_id_str}"
                "?format=csv&labels=both"
            )

            api_url_ter = (
                f"https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data/"
                f"{agency},{dataflow_id},1.0/{indicator_id_str}..{geography_str}."
                "?format=csv&labels=both"
            )

            
            st.write(f"Fetching data for dataflow: {flow}")
            st.code(api_url)
            response = requests.get(api_url)

            if response.status_code == 200:
                try:
                    df_data_flow = pd.read_csv(StringIO(response.text))
                    # Convert OBS_VALUE to float, if present.
                    if "OBS_VALUE" in df_data_flow.columns:
                        df_data_flow["OBS_VALUE"] = pd.to_numeric(df_data_flow["OBS_VALUE"], errors="coerce")
                    df_data_flow["dataflow"] = flow
                    flow_data[flow] = df_data_flow
                except Exception as e:
                    st.error(f"Error reading CSV data for {flow}: {e}")
            else:
                st.error(f"API call for dataflow {flow} failed with status code: {response.status_code}. Trying fallback API.")
                st.code(api_url_bis)
                fallback_response = requests.get(api_url_bis)
                if fallback_response.status_code == 200:
                    try:
                        df_data_flow = pd.read_csv(StringIO(fallback_response.text))
                        if "OBS_VALUE" in df_data_flow.columns:
                            df_data_flow["OBS_VALUE"] = pd.to_numeric(df_data_flow["OBS_VALUE"], errors="coerce")
                        df_data_flow["dataflow"] = flow
                        flow_data[flow] = df_data_flow
                    except Exception as e:
                        st.error(f"Error reading CSV data for {flow} using fallback: {e}")
                else:
                    st.error(f"Fallback API call for dataflow {flow} failed with status code: {fallback_response.status_code}. Trying tertiary API.")
                    st.code(api_url_ter)
                    tertiary_response = requests.get(api_url_ter)
                    if tertiary_response.status_code == 200:
                        try:
                            df_data_flow = pd.read_csv(StringIO(tertiary_response.text))
                            if "OBS_VALUE" in df_data_flow.columns:
                                df_data_flow["OBS_VALUE"] = pd.to_numeric(df_data_flow["OBS_VALUE"], errors="coerce")
                            df_data_flow["dataflow"] = flow
                            flow_data[flow] = df_data_flow
                        except Exception as e:
                            st.error(f"Error reading CSV data for {flow} using tertiary fallback: {e}")
                    else:
                        st.error(f"Tertiary API call for dataflow {flow} failed with status code: {tertiary_response.status_code}")

            if flow_data:
                st.session_state["flow_data"] = flow_data


##############################################
# Step 5: Display and Visualize Data for Each Dataflow
##############################################
if "flow_data" in st.session_state:
    st.subheader("Fetched Data by Dataflow")
    for flow, df_data in st.session_state["flow_data"].items():
        # ---- Standardize Geographical Area Column Names ----
        # Rename any column found in synonyms to "Geographical area"
        rename_dict = {}
        synonyms = ["Country", "Geographic area", "Geo area", "Reference Areas","Areas"]
        for col in synonyms:
            if col in df_data.columns and col != "Geographical area":
                rename_dict[col] = "Geographical area"
        if rename_dict:
            df_data.rename(columns=rename_dict, inplace=True)
    

    for flow, df_data in st.session_state["flow_data"].items():
        # Rename any column found in synonyms to "Indicator"
        rename_dict = {}
        synonyms = ["Coverage Indicators","Coverage indicators"]
        for col in synonyms:
            if col in df_data.columns and col != "Indicator":
                rename_dict[col] = "Indicator"
        if rename_dict:
            df_data.rename(columns=rename_dict, inplace=True)

        # --- Show Available Indicators ---
        unique_indicators = sorted(df_data["Indicator"].dropna().unique(), key=lambda x: str(x))
        with st.expander(f"**Data for {flow} – indicators:** {' / '.join(unique_indicators)}", expanded=True):
            st.dataframe(df_data)

            # Add a download button for this dataflow
            csv_data = df_data.to_csv(index=False).encode("utf-8")
            st.download_button(label="Download data as CSV", data=csv_data, file_name=f"{flow}_data.csv", mime="text/csv", key=f"download_{flow}")
            
            st.markdown("### Data filtering")
            available_columns = df_data.columns.tolist()
            

            # --- Interactive Filter with Empty Default ---
            # If "SEX" exists and has >1 unique value, prefill with "SEX"
            if "SEX" in available_columns and df_data["SEX"].nunique() > 1:
                default_filter_field = "SEX"
                default_filter_index = available_columns.index("SEX") + 1
            else:
                default_filter_field = ""
                default_filter_index = 0
            
            filter_field_options = [""] + available_columns
            filter_field = st.selectbox(f"Select field to filter by for {flow}", filter_field_options, index=default_filter_index, key=f"filter_field_{flow}")
            if filter_field != "":
                filter_options = sorted(df_data[filter_field].dropna().unique(), key=lambda x: str(x))
                if filter_field == "SEX" and "_T" in filter_options:
                    default_filter_value = "_T"
                else:
                    default_filter_value = filter_options[0]
                selected_filter_value = st.selectbox(f"Select value for '{filter_field}' for {flow}", filter_options, index=filter_options.index(default_filter_value), key=f"filter_value_{flow}")
                df_filtered_vis = df_data[df_data[filter_field] == selected_filter_value]
            else:
                df_filtered_vis = df_data
            
            st.markdown("### Graph layout")
            # --- Axis Defaults ---
            default_x = available_columns.index("TIME_PERIOD") if "TIME_PERIOD" in available_columns else 0
            default_y = available_columns.index("OBS_VALUE") if "OBS_VALUE" in available_columns else 0
            
            # --- Determine Color Grouping or Chart Title Based on Indicator Count ---
            chart_title = None
            group_options = ["None"] + available_columns
            # First, check if "Geographical area" exists and has several unique values.
            if "Geographical area" in available_columns and df_filtered_vis["Geographical area"].nunique() > 1:
                default_index = group_options.index("Geographical area")
                group_col = st.selectbox(f"Select Color Grouping Column (optional) for {flow}", group_options, index=default_index, key=f"group_{flow}")
                st.info(f"For {flow}: Multiple unique geographical areas detected. Defaulting color grouping to 'Geographical area'.")
            elif "Indicator" in available_columns:
                if df_filtered_vis["Indicator"].nunique() > 1:
                    default_index = group_options.index("Indicator") if "Indicator" in group_options else 0
                    group_col = st.selectbox(f"Select Color Grouping Column (optional) for {flow}", group_options, index=default_index, key=f"group_{flow}")
                    st.info(f"For {flow}: Multiple unique indicators detected. Defaulting color grouping to 'Indicator'.")
                else:
                    unique_indicator = df_filtered_vis["Indicator"].unique()[0]
                    chart_title = unique_indicator
                    group_col = st.selectbox(f"Select Color Grouping Column (optional) for {flow}", group_options, index=0, key=f"group_{flow}")
            else:
                default_group = (group_options.index("Reference Areas") 
                                 if ("Reference Areas" in available_columns and df_filtered_vis["Reference Areas"].nunique() > 1)
                                 else (group_options.index("sex") if "sex" in group_options else 0))
                group_col = st.selectbox(f"Select Color Grouping Column (optional) for {flow}", group_options, index=default_group, key=f"group_{flow}")
            
            # --- Chart Type and Axis Selections ---
            chart_types = ["Line Chart", "Bar Chart", "Scatter Plot"]
            default_chart_index = 0 if len(df_filtered_vis) > 1 else 1
            chart_type = st.selectbox(f"Select Chart Type for {flow}", chart_types, index=default_chart_index, key=f"chart_type_{flow}")
            x_axis = st.selectbox(f"Select X-axis Column for {flow}", available_columns, index=default_x, key=f"x_axis_{flow}")
            y_axis = st.selectbox(f"Select Y-axis Column for {flow}", available_columns, index=default_y, key=f"y_axis_{flow}")
            
            # Automatically generate the graph based on the selections
            if group_col != "None":
                df_agg = df_filtered_vis.groupby([x_axis, group_col], as_index=False)[y_axis].mean()
            else:
                df_agg = df_filtered_vis.groupby(x_axis, as_index=False)[y_axis].mean()
            
            if chart_type == "Bar Chart":
                fig = px.bar(df_agg, x=x_axis, y=y_axis, color=(group_col if group_col != "None" else None), barmode="group")
            elif chart_type == "Line Chart":
                fig = px.line(df_agg, x=x_axis, y=y_axis, color=(group_col if group_col != "None" else None), markers=True)
            elif chart_type == "Scatter Plot":
                fig = px.scatter(df_agg, x=x_axis, y=y_axis, color=(group_col if group_col != "None" else None))
            else:
                st.info("Unsupported chart type selected.")
                fig = None
            
            if fig is not None and chart_title:
                # Left-align the title (x=0 with left anchor)
                fig.update_layout(title_text=chart_title, title_x=0, title_xanchor="left", title_font=dict(size=20))
            
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True, key=f"plotly_chart_{flow}")

            print(chart_title)
            print(df_filtered_vis["Indicator"].nunique())
