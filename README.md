# Building Density Calculator

A Streamlit app that counts OpenStreetMap buildings within a radius and computes density per area, with an interactive map.

## Run
```powershell
cd C:\Users\baahj\Density
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Use
- In the sidebar: choose Address or Coordinates
- Enter address or lat/lon
- Set radius and units (km/mi)
- Click "Calculate"

If nothing appears, ensure you clicked Calculate and check the terminal for errors. Overpass API limits can cause temporary failures. Try a smaller radius first. "# density" 
"# density" 
