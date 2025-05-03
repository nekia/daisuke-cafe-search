import React, { useState, useRef, useEffect } from 'react';
import { GoogleMap, LoadScript, Marker, InfoWindow } from '@react-google-maps/api';

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
    const [currentLocation, setCurrentLocation] = useState(null);
    const mapRef = useRef(null);

    useEffect(() => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude, longitude } = position.coords;
                    setCurrentLocation({ lat: latitude, lng: longitude });
                    setPosition({ lat: latitude, lng: longitude });
                },
                (error) => {
                    console.error("Error getting current location:", error);
                }
            );
        }
    }, []);

    const handleMapLoad = (map) => {
        mapRef.current = map;
    };

    const handleCenter = () => {
        if (!mapRef.current) return;
        const newPos = mapRef.current.getCenter().toJSON();
        if (newPos.lat === position.lat && newPos.lng === position.lng) return;
        setPosition(newPos);
    };

    const createKey = (location) => location.lat + location.lng;

    return (
        <LoadScript googleMapsApiKey={process.env.REACT_APP_GOOGLE_MAPS_API_KEY}>
            <GoogleMap
                mapContainerStyle={mapContainerStyle}
                center={position}
                zoom={13}
                options={{
                    gestureHandling: 'greedy',
                    streetViewControl: false, // Disable StreetView
                    fullscreenControl: false
                }}
                onLoad={handleMapLoad}
                onDragEnd={handleCenter}
            >
                {currentLocation && (
                    <Marker
                        position={currentLocation}
                        icon={{
                            url: 'http://maps.google.com/mapfiles/ms/icons/green-dot.png',
                            scaledSize: new window.google.maps.Size(40, 40)
                        }}
                    />
                )}
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
                    />
                ))}

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