import React, { useEffect, useRef, useState } from 'react';
import { GoogleMap, Marker, InfoWindow } from '@react-google-maps/api';

const PARKING_STROKE = {
    'パーキング・メーター': '#1565c0',
    'パーキング・チケット': '#ef6c00',
};

const ParkingInfoContent = ({ props }) => {
    if (!props) return null;

    const rows = [
        ['種別', props.kind],
        ['利用時間', props.hours],
        ['制限時間', props.limitMinutes != null ? `${props.limitMinutes}分` : null],
        ['手数料', props.fee != null ? `${props.fee}円` : null],
        ['制限事項', [props.note1, props.note2].filter(Boolean).join(' / ') || null],
    ].filter(([, value]) => value);

    const vehicleBits = [];
    if (props.car) vehicleBits.push('普通車');
    if (props.freight) vehicleBits.push('貨物');
    if (props.motorcycle) vehicleBits.push('二輪');
    if (props.disability) vehicleBits.push('標章車専用');
    if (vehicleBits.length) {
        rows.push(['対象', vehicleBits.join('・')]);
    }

    return (
        <div style={{ fontSize: 13, lineHeight: 1.45, maxWidth: 240 }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>時間制限駐車区間</div>
            {rows.map(([label, value]) => (
                <div key={label}>
                    <span style={{ color: '#666' }}>{label}:</span> {value}
                </div>
            ))}
            <div style={{ marginTop: 6, color: '#888', fontSize: 11 }}>
                参考: オープンデータ（2025-10-01）
            </div>
        </div>
    );
};

const MapComponent = ({
    places = [],
    categoryColors,
    center,
    onCenterChange,
    currentLocation,
    showParkingMeters = false,
}) => {
    const mapContainerStyle = {
        height: '100%',
        width: '100%',
        position: 'absolute',
        left: 0,
        top: 0,
    };

    const [selected, setSelected] = useState(null);
    const [parkingInfo, setParkingInfo] = useState(null);
    const [mapReady, setMapReady] = useState(false);
    const mapRef = useRef(null);
    const parkingClickListenerRef = useRef(null);
    const parkingGeoJsonRef = useRef(null);

    const clearParkingOverlay = () => {
        const map = mapRef.current;
        if (!map || !window.google?.maps) return;
        map.data.forEach((feature) => {
            if (feature.getProperty('__parkingMeter')) {
                map.data.remove(feature);
            }
        });
        if (parkingClickListenerRef.current) {
            window.google.maps.event.removeListener(parkingClickListenerRef.current);
            parkingClickListenerRef.current = null;
        }
        setParkingInfo(null);
    };

    const handleMapLoad = (map) => {
        mapRef.current = map;
        setMapReady(true);
    };

    useEffect(() => {
        if (!mapReady) return undefined;

        const map = mapRef.current;
        if (!map || !window.google?.maps) return undefined;

        let cancelled = false;

        const applyParkingOverlay = async () => {
            if (!showParkingMeters) {
                clearParkingOverlay();
                return;
            }

            if (!parkingGeoJsonRef.current) {
                const module = await import('./data/parkingmeter.json');
                parkingGeoJsonRef.current = module.default || module;
            }
            if (cancelled || !mapRef.current) return;

            clearParkingOverlay();

            const features = map.data.addGeoJson(parkingGeoJsonRef.current);
            features.forEach((feature) => {
                feature.setProperty('__parkingMeter', true);
            });

            map.data.setStyle((feature) => {
                if (!feature.getProperty('__parkingMeter')) {
                    return {};
                }
                const kind = feature.getProperty('kind');
                return {
                    strokeColor: PARKING_STROKE[kind] || '#c62828',
                    strokeOpacity: 0.85,
                    strokeWeight: 4,
                    clickable: true,
                    zIndex: 1,
                };
            });

            parkingClickListenerRef.current = map.data.addListener('click', (event) => {
                const feature = event.feature;
                if (!feature?.getProperty('__parkingMeter')) return;
                setSelected(null);
                setParkingInfo({
                    position: {
                        lat: event.latLng.lat(),
                        lng: event.latLng.lng(),
                    },
                    props: {
                        kind: feature.getProperty('kind'),
                        hours: feature.getProperty('hours'),
                        limitMinutes: feature.getProperty('limitMinutes'),
                        fee: feature.getProperty('fee'),
                        note1: feature.getProperty('note1'),
                        note2: feature.getProperty('note2'),
                        car: feature.getProperty('car'),
                        freight: feature.getProperty('freight'),
                        motorcycle: feature.getProperty('motorcycle'),
                        disability: feature.getProperty('disability'),
                    },
                });
            });
        };

        applyParkingOverlay();

        return () => {
            cancelled = true;
            clearParkingOverlay();
        };
        // clearParkingOverlay closes over stable refs/setters
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [showParkingMeters, mapReady]);

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
                            setParkingInfo(null);
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
                        {(selected.businessStatus === 'CLOSED_PERMANENTLY' ||
                          selected.businessStatus === 'CLOSED_TEMPORARILY') && (
                            <>
                                <span style={{ color: '#c62828', fontWeight: 600 }}>
                                    {selected.refreshMeta?.placeIdInvalid
                                        ? '閉業（Place ID無効）'
                                        : selected.businessStatus === 'CLOSED_PERMANENTLY'
                                          ? '閉業'
                                          : '臨時休業'}
                                </span>
                                <br/>
                            </>
                        )}
                        {selected.url && (
                            <a href={selected.url} target="_blank" rel="noopener noreferrer">詳細</a>
                        )}
                    </div>
                </InfoWindow>
            )}
            {parkingInfo && (
                <InfoWindow
                    position={parkingInfo.position}
                    onCloseClick={() => setParkingInfo(null)}
                >
                    <ParkingInfoContent props={parkingInfo.props} />
                </InfoWindow>
            )}
        </GoogleMap>
    );
};

export default MapComponent;
