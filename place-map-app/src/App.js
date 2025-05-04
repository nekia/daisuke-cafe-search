import React, { useEffect, useState } from 'react';
import Select from 'react-select';
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';
import { jwtDecode } from 'jwt-decode';  // 名前付きエクスポートとしてインポート
import MapComponent from './MapComponent';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
// import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFnsV3';
import jaLocale from 'date-fns/locale/ja';
import TextField from '@mui/material/TextField';
import Checkbox from '@mui/material/Checkbox';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import ListItemIcon from '@mui/material/ListItemIcon';
import Paper from '@mui/material/Paper';
import PlaceCard from './components/PlaceCard';
import Typography from '@mui/material/Typography';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { LoadScript } from '@react-google-maps/api';

const App = () => {
    const [places, setPlaces] = useState([]);
    const [primaryTypes, setPrimaryTypes] = useState([]);
    const [filter, setFilter] = useState([]);
    const [category, setCategory] = useState(['1', '2']);
    const [selectedDateTime, setSelectedDateTime] = useState(new Date());
    const [isDateTimeFilterEnabled, setIsDateTimeFilterEnabled] = useState(true);
    // const [showOpenNow, setShowOpenNow] = useState(false);
    const [user, setUser] = useState(null);
    const [token, setToken] = useState(null);
    const [isTypeDialogOpen, setIsTypeDialogOpen] = useState(false);
    const allowedEmails = ['nekiaiken@gmail.com', 'nekiaiyaiken@gmail.com', 'kumatsushi@gmail.com'];  // 許可されたメールアドレスのリスト
    const backendEndpoint = process.env.REACT_APP_BACKEND_ENDPOINT;
    const defaultPosition = { lat: 35.681236, lng: 139.767125 };
    const [currentLocation, setCurrentLocation] = useState(defaultPosition);
    const [sortedPlaces, setSortedPlaces] = useState([]);
    const [position, setPosition] = useState(defaultPosition);
    const [viewMode, setViewMode] = useState('map'); // 'map' or 'list'

    const categoryColors = {
        '1': 'red',
        '2': 'blue',
        // 他のカテゴリと色を追加
    };

    useEffect(() => {
        const storedToken = localStorage.getItem('authToken');
        if (storedToken) {
            const decodedToken = jwtDecode(storedToken);
            const currentTime = Date.now() / 1000; // 現在の時刻を秒単位で取得
            console.log(`Expired after ${decodedToken.exp - currentTime} secs`)
            console.log(`now : ${new Date().toString()}`);
            if (decodedToken.exp > currentTime && allowedEmails.includes(decodedToken.email)) {
                setUser(decodedToken);
                setToken(storedToken);
            } else {
                handleLogout();
            }
        }
    }, []);

    useEffect(() => {
        console.log(`backendEndpoint: ${backendEndpoint}`)
        if (token) {
            fetchPlaces(filter, category, isDateTimeFilterEnabled ? selectedDateTime : null);
            fetchPrimaryTypes();
        }
    }, [token]);

    const fetchPlaces = (types, category, dateTime) => {
        let query = types.map(type => `primary_type=${type}`).join('&');
        query += '&'
        query += category.map(cat => `category=${cat}`).join('&');
        if (dateTime) {
            query += `&dateTime=${dateTime.toISOString()}`;
        }
        fetch(`${backendEndpoint}/places?${query}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        })
            .then(response => response.json())
            .then(data => setPlaces(data));
    };

    const fetchPrimaryTypes = () => {
        fetch(`${backendEndpoint}/primary_types`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        })
            .then(response => response.json())
            .then(data => setPrimaryTypes(data.map(type => ({ value: type, label: type }))));
    };

    const handleFilterChange = (selectedOptions) => {
        const selectedValues = selectedOptions ? selectedOptions.map(option => option.value) : [];
        setFilter(selectedValues);
        fetchPlaces(selectedValues, category, isDateTimeFilterEnabled ? selectedDateTime : null);

        // const query = selectedValues.map(type => `primary_type=${type}`).join('&');
        // fetch(`http://localhost:3001/places?${query}`)
        //     .then(response => response.json())
        //     .then(data => setPlaces(data));
    };

    const handleCategoryChange = (selectedOptions) => {
        const selectedValues = selectedOptions ? selectedOptions.map(option => option.value) : [];
        setCategory(selectedValues);
        fetchPlaces(filter, selectedValues, isDateTimeFilterEnabled ? selectedDateTime : null);

        // const query = selectedValues.map(type => `primary_type=${type}`).join('&');
        // fetch(`http://localhost:3001/places?${query}`)
        //     .then(response => response.json())
        //     .then(data => setPlaces(data));
    };

    const handleDateTimeChange = (date) => {
        setSelectedDateTime(date);
        fetchPlaces(filter, category, isDateTimeFilterEnabled ? date : null);
    };

    const handleLoginSuccess = (response) => {
        const decodedToken = jwtDecode(response.credential);
        if (allowedEmails.includes(decodedToken.email)) {
            setUser(decodedToken);
            setToken(response.credential);
            localStorage.setItem('authToken', response.credential); // トークンをローカルストレージに保存
        } else {
            alert('このアカウントではログインできません。');
            handleLogout();
        }
    };

    const handleLoginFailure = (response) => {
        console.error(response);
    };

    const handleLogout = () => {
        setUser(null);
        setToken(null);
        localStorage.removeItem('authToken'); // ローカルストレージからトークンを削除
    };
    
    const handleDateTimeFilterToggle = () => {
        setIsDateTimeFilterEnabled(!isDateTimeFilterEnabled);
        if (!isDateTimeFilterEnabled) {
            fetchPlaces(filter, category, selectedDateTime);
        } else {
            fetchPlaces(filter, category, null);
        }
    };
    
    const handleResetDateTime = () => {
        const now = new Date();
        setSelectedDateTime(now);
        if (isDateTimeFilterEnabled) {
            fetchPlaces(filter, category, now);
        }
    };

    const handleTypeDialogOpen = () => {
        setIsTypeDialogOpen(true);
    };

    const handleTypeDialogClose = () => {
        setIsTypeDialogOpen(false);
    };

    const handleTypeSelect = (type) => {
        const newFilter = filter.includes(type)
            ? filter.filter(t => t !== type)
            : [...filter, type];
        setFilter(newFilter);
        fetchPlaces(newFilter, category, isDateTimeFilterEnabled ? selectedDateTime : null);
    };

    // 現在地を取得する関数
    const getCurrentLocation = () => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    setCurrentLocation({
                        lat: position.coords.latitude,
                        lng: position.coords.longitude
                    });
                },
                (error) => {
                    console.error('位置情報の取得に失敗しました:', error);
                }
            );
        }
    };

    // 2点間の距離を計算する関数（km単位）
    const calculateDistance = (lat1, lng1, lat2, lng2) => {
        const R = 6371; // 地球の半径（km）
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLng = (lng2 - lng1) * Math.PI / 180;
        const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                Math.sin(dLng/2) * Math.sin(dLng/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        return R * c;
    };

    // 店舗を距離順にソート
    useEffect(() => {
        if (currentLocation && places.length > 0) {
            const placesWithDistance = places
                .filter(place => place && place.location && place.location.latitude && place.location.longitude)
                .map(place => ({
                    ...place,
                    distance: calculateDistance(
                        currentLocation.lat,
                        currentLocation.lng,
                        place.location.latitude,
                        place.location.longitude
                    )
                }));
            const sorted = [...placesWithDistance].sort((a, b) => a.distance - b.distance);
            setSortedPlaces(sorted);
        } else {
            setSortedPlaces([]);
        }
    }, [places, currentLocation]);

    // コンポーネントマウント時に現在地を取得
    useEffect(() => {
        getCurrentLocation();
    }, []);

    // カードクリック時の処理
    const handleCardClick = (place) => {
        if (!place || !place.location) {
            alert('位置情報が取得できませんでした。');
            return;
        }
        setPosition({
            lat: place.location.latitude,
            lng: place.location.longitude
        });
    };

    if (!user) {
        return (
            <GoogleOAuthProvider clientId={process.env.REACT_APP_GOOGLE_CLIENT_ID}>
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
                    <GoogleLogin
                        onSuccess={handleLoginSuccess}
                        onFailure={handleLoginFailure}
                        cookiePolicy={'single_host_origin'}
                    />
                </div>
            </GoogleOAuthProvider>
        );
    }

    return (
        <GoogleOAuthProvider clientId={process.env.REACT_APP_GOOGLE_CLIENT_ID}>
            <LoadScript googleMapsApiKey={process.env.REACT_APP_GOOGLE_MAPS_API_KEY}>
                <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
                    <nav style={{ position: 'fixed', top: 0, width: '100%', zIndex: 10, backgroundColor: '#fff', padding: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                            <Button
                                variant="outlined"
                                onClick={handleTypeDialogOpen}
                                style={{ marginRight: '10px', height: '40px' }}
                            >
                                タイプを選択
                            </Button>
                            <Select
                                isMulti
                                options={[{ value: 1, label: '店内OK' }, { value: 2, label: '外席OK' }]}
                                onChange={handleCategoryChange}
                                placeholder="Select category..."
                                styles={{ container: (provided) => ({ ...provided, height: '40px', marginRight: '10px' }) }}
                            />
                            <FormControlLabel
                                control={
                                    <Checkbox
                                        checked={isDateTimeFilterEnabled}
                                        onChange={handleDateTimeFilterToggle}
                                    />
                                }
                                label="営業中"
                                style={{ marginLeft: '0px' }}
                            />
                            <LocalizationProvider dateAdapter={AdapterDateFns} locale={jaLocale}>
                                <DateTimePicker
                                    value={selectedDateTime}
                                    onChange={handleDateTimeChange}
                                    disabled={!isDateTimeFilterEnabled}
                                    slotProps={{
                                        textField: { style: { marginLeft: '20px', height: '40px' } }
                                    }}
                                />
                            </LocalizationProvider>
                            <Button onClick={handleResetDateTime} style={{ marginLeft: '0px', height: '40px' }}>Now</Button>
                            <ToggleButtonGroup
                                value={viewMode}
                                exclusive
                                onChange={(_, next) => next && setViewMode(next)}
                                style={{ marginLeft: 20 }}
                            >
                                <ToggleButton value="map">地図</ToggleButton>
                                <ToggleButton value="list">リスト</ToggleButton>
                            </ToggleButtonGroup>
                        </div>
                        <div>
                            {user ? (
                                <div>
                                    {user.name}
                                    <button onClick={handleLogout} style={{ marginLeft: '10px' }}>Logout</button>
                                </div>
                            ) : (
                                <GoogleLogin
                                    onSuccess={handleLoginSuccess}
                                    onFailure={handleLoginFailure}
                                    cookiePolicy={'single_host_origin'}
                                />
                            )}
                        </div>
                    </nav>
                    <Dialog
                        open={isTypeDialogOpen}
                        onClose={handleTypeDialogClose}
                        maxWidth="sm"
                        fullWidth
                    >
                        <DialogTitle>タイプを選択</DialogTitle>
                        <DialogContent>
                            <List>
                                {primaryTypes.map((type) => (
                                    <ListItem key={type.value} disablePadding>
                                        <ListItemButton onClick={() => handleTypeSelect(type.value)}>
                                            <ListItemIcon>
                                                <Checkbox
                                                    edge="start"
                                                    checked={filter.includes(type.value)}
                                                    tabIndex={-1}
                                                    disableRipple
                                                />
                                            </ListItemIcon>
                                            <ListItemText primary={type.label} />
                                        </ListItemButton>
                                    </ListItem>
                                ))}
                            </List>
                        </DialogContent>
                        <DialogActions>
                            <Button onClick={handleTypeDialogClose}>閉じる</Button>
                        </DialogActions>
                    </Dialog>
                    <div style={{ display: 'flex', flex: '1', marginTop: '60px' }}>
                        {viewMode === 'map' ? (
                            <div style={{ flex: '1', position: 'relative' }}>
                                <MapComponent
                                    key={viewMode}
                                    places={places}
                                    categoryColors={categoryColors}
                                    center={position}
                                    onCenterChange={setPosition}
                                    currentLocation={currentLocation}
                                />
                            </div>
                        ) : (
                            <Paper 
                                elevation={3} 
                                style={{ 
                                    width: '100%',
                                    maxWidth: '600px',
                                    margin: '0 auto',
                                    padding: '20px',
                                    overflowY: 'auto',
                                    backgroundColor: '#fff',
                                    height: 'calc(100vh - 80px)',
                                    boxSizing: 'border-box',
                                    display: 'flex',
                                    flexDirection: 'column',
                                }}
                            >
                                <Typography variant="h6" gutterBottom style={{ marginBottom: '20px' }}>
                                    近くの店舗
                                </Typography>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', width: '100%' }}>
                                    {sortedPlaces.map((place) => (
                                        <PlaceCard
                                            key={place.id || `${place.location.latitude}-${place.location.longitude}`}
                                            place={place}
                                            distance={place.distance}
                                            onClick={() => handleCardClick(place)}
                                        />
                                    ))}
                                </div>
                            </Paper>
                        )}
                    </div>
                </div>
            </LoadScript>
        </GoogleOAuthProvider>
    );
};

export default App;