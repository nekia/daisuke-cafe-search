import React, { useState, useRef } from 'react';
import { GoogleMap, LoadScript, Marker, InfoWindow, MarkerClusterer } from '@react-google-maps/api';

const MapComponent = ({ places, categoryColors }) => {
    const mapContainerStyle = {
        height: '100vh',
        width: '100vw'
    };

    const [position, setPosition] = useState({
        lat: 35.6895,
        lng: 139.6917
    });
  
    const [selected, setSelected] = useState(null);
    const mapRef = useRef(null);

    const handleMapLoad = (map) => {
        mapRef.current = map;
    };

    const handleCenter = () => {
        if (!mapRef.current) return;
    
        
        const newPos = mapRef.current.getCenter().toJSON();
        if (newPos.lat === position.lat && newPos.lng === position.lng) return
        setPosition(newPos);
    }

    const createKey = (location) => location.lat + location.lng;
    const clusterStyles = [
        {
          textColor: "white",
        //   url: "path/to/smallclusterimage.png",
          height: 50,
          width: 50,
        },
        {
          textColor: "white",
        //   url: "path/to/mediumclusterimage.png",
          height: 50,
          width: 50,
        },
        {
          textColor: "white",
        //   url: "path/to/largeclusterimage.png",
          height: 50,
          width: 50,
        },
    ];

    return (
        <LoadScript googleMapsApiKey={process.env.REACT_APP_GOOGLE_MAPS_API_KEY}>
            <GoogleMap
                mapContainerStyle={mapContainerStyle}
                center={position} // Use defaultCenter instead of center
                zoom={13}
                options={{
                    gestureHandling: 'greedy' // フリック操作を可能にする設定
                }}
                onLoad={handleMapLoad}
                onDragEnd={handleCenter}
            >
                <MarkerClusterer
                    // options={{
                    //     imagePath: 'https://developers.google.com/maps/documentation/javascript/examples/markerclusterer/m',
                    // }}
                    options={{
                        gridSize: 50,
                        styles: clusterStyles,
                        maxZoom: 15,
                    }}
                >
                    {(clusterer) =>
                        {places.map(place => (
                            <Marker 
                                key={createKey(place.location)}
                                position={{ lat: place.location.latitude, lng: place.location.longitude }}
                                onClick={() => {
                                    setSelected(place);
                                }}
                                icon={{
                                    url: `http://maps.google.com/mapfiles/ms/icons/${categoryColors[place.category] || 'red'}-dot.png`
                                }}
                                clusterer={clusterer}
                            />
                        ))}
                    }
                </MarkerClusterer>

                {selected ? (
                    <InfoWindow
                        position={{
                            lat: selected.location.latitude,
                            lng: selected.location.longitude,
                        }}
                        onCloseClick={() => {
                            setSelected(null);
                        }}
                    >
                        <div>
                            {selected.location_name.text}<br/>
                            <a href={selected.url} target="_blank" rel="noopener noreferrer">Link</a>
                        </div>
                    </InfoWindow>
                ) : null}
            </GoogleMap>
        </LoadScript>
    );
};

export default MapComponent;