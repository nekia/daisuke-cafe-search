import React, { useRef, useState } from 'react';
import { GoogleMap, Marker, InfoWindow } from '@react-google-maps/api';

const MapComponent = ({ places = [], categoryColors, center, onCenterChange, currentLocation }) => {
    const mapContainerStyle = {
        height: '100vh',
        width: '100vw'
    };

    const [selected, setSelected] = useState(null);
    const mapRef = useRef(null);

    const handleMapLoad = (map) => {
        mapRef.current = map;
    };

    const handleCenter = () => {
        if (!mapRef.current) return;
        const newPos = mapRef.current.getCenter().toJSON();
        if (onCenterChange) {
            onCenterChange(newPos);
        }
    };

    const createKey = (place) => {
        if (!place) return Math.random().toString();
        if (place.id) return place.id;
        if (place.location && place.location.latitude && place.location.longitude) {
            return `${place.location.latitude}-${place.location.longitude}-${Math.random().toString(36).substr(2, 9)}`;
        }
        return Math.random().toString();
    };

    const getMarkerIcon = (color) => {
        return {
            url: `http://maps.google.com/mapfiles/ms/icons/${color}-dot.png`,
            scaledSize: new window.google.maps.Size(40, 40)
        };
    };

    const getMarkerPosition = (place) => {
        if (!place || !place.location) {
            return null;
        }
        return {
            lat: place.location.latitude,
            lng: place.location.longitude
        };
    };

    const validPlaces = places.filter(place => {
        const position = getMarkerPosition(place);
        return position !== null;
    });

    return (
        <GoogleMap
            mapContainerStyle={mapContainerStyle}
            center={center}
            zoom={13}
            options={{
                gestureHandling: 'greedy',
                streetViewControl: false,
                fullscreenControl: false
            }}
            onLoad={handleMapLoad}
            onDragEnd={handleCenter}
        >
            <Marker
                position={currentLocation}
                icon={getMarkerIcon('green')}
            />
            {validPlaces.map(place => {
                const position = getMarkerPosition(place);
                if (!position) return null;
                return (
                    <Marker 
                        key={createKey(place)}
                        position={position}
                        onClick={() => {
                            setSelected(place);
                        }}
                        icon={getMarkerIcon(categoryColors[place.category] || 'red')}
                    />
                );
            })}
            {selected && (
                <InfoWindow
                    position={getMarkerPosition(selected)}
                    onCloseClick={() => {
                        setSelected(null);
                    }}
                >
                    <div>
                        {selected.location_name?.text || '店舗名なし'}<br/>
                        {selected.url && (
                            <a href={selected.url} target="_blank" rel="noopener noreferrer">詳細</a>
                        )}
                    </div>
                </InfoWindow>
            )}
        </GoogleMap>
    );
};

export default MapComponent;