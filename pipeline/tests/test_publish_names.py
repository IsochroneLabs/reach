import geopandas as gpd
import pandas as pd
import shapely

from reach_pipeline.stages.publish import with_names


def test_unnamed_destinations_get_their_type_label() -> None:
    dest = gpd.GeoDataFrame(
        {
            "destination_id": ["doctor:n1", "park:w1", "grocery:1"],
            "destination_type": ["doctor", "park", "grocery"],
            "name": ["", "Stadtpark", None],
        },
        geometry=[shapely.Point(0, 0)] * 3,
        crs="EPSG:25832",
    )
    types = pd.DataFrame(
        {
            "destination_type": ["doctor", "park", "grocery"],
            "label_en": ["Doctor", "Park", "Supermarket"],
        }
    )
    out = with_names(dest, types)
    assert out["name"].tolist() == ["Doctor", "Stadtpark", "Supermarket"]
