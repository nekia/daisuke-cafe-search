import React, { useCallback, useEffect, useState } from 'react';
import Select from 'react-select';
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';
import { jwtDecode } from 'jwt-decode';  // 名前付きエクスポートとしてインポート
import MapComponent from './MapComponent';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
// import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFnsV3';
import jaLocale from 'date-fns/locale/ja';
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
import Box from '@mui/material/Box';
import useMediaQuery from '@mui/material/useMediaQuery';
import { LoadScript } from '@react-google-maps/api';
import primaryTypeTextCatalog from './data/primary_type_text.json';

/** `primary_type_text.json` の表記のみ（綴り違いはここで落ちる） */
const PRIMARY_TYPE_TEXT_CATALOG = new Set(primaryTypeTextCatalog);

/**
 * DB の primary_type.text（日本語等）に合わせたプリセット。
 * 候補は primary_type_text.json に含まれるものだけ下書きへ載る（API の distinct と交差）。
 */
const TYPE_FILTER_PRESET_SPECS = [
    {
        id: 'cafe_sweets',
        label: 'カフェ・スイーツ',
        types: [
            'Cafe',
            'アイスクリーム店',
            'カフェテリア',
            'カフェ・喫茶',
            'ケーキ屋',
            'コーヒー スタンド',
            'コーヒーショップ・喫茶店',
            'ジュースバー',
            'スイーツ店',
            'チョコレート ショップ',
            'ティーハウス',
            'デザート ショップ',
            '洋菓子店',
            'ベーカリー',
            'ベーグル専門店',
            'ドーナツ店',
            '菓子店',
        ],
    },
    {
        id: 'asian',
        label: 'アジア料理',
        types: [
            'アジア料理店',
            'インドネシア料理店',
            'インド料理店',
            'タイ料理店',
            '台湾料理店',
            '中華料理店',
            '南インド料理店',
            'ベトナム料理店',
            '和食店',
            '寿司店',
            '広東料理店',
            '点心店',
            '焼き鳥店',
            '焼肉店',
            '韓国料理店',
            'ラーメン屋',
            '飲茶・点心店',
        ],
    },
    {
        id: 'washoku',
        label: '和食',
        types: ['和食店', '寿司店', '焼き鳥店', '焼肉店', 'ラーメン屋'],
    },
    {
        id: 'western',
        label: '欧米・多国籍レストラン',
        types: [
            'アメリカ料理店',
            'イタリア料理店',
            'アフリカ料理店',
            'ステーキハウス',
            'スペイン料理店',
            'ドイツ料理店',
            'フランス料理店',
            'メキシコ料理店',
            'ブラジル料理店',
            'レストラン',
            '洋食レストラン',
            'ファミリー レストラン',
            'ファースト フード店',
            'ビストロ',
            'ダイナー',
            'ビュッフェ レストラン',
            'ブランチ レストラン',
            '朝食レストラン',
            '地中海料理店',
            'ギリシャ料理店',
            'ベルギー料理店',
            'トルコ料理店',
            '中東料理店',
            'ハンバーガー店',
            'ピザ店',
            'ビーガン料理店',
            'ベジタリアン料理店',
            'シーフード・海鮮料理店',
        ],
    },
    {
        id: 'bar_izakaya',
        label: 'バー・居酒屋',
        types: ['バー', 'パブ', 'ワインバー', 'バー＆グリル', '居酒屋', '酒店'],
    },
    {
        id: 'casual_takeaway',
        label: '軽食・テイクアウト',
        types: ['サンドイッチ店', 'カレー店', 'テイクアウト', '軽食店'],
    },
    {
        id: 'park_green_dog',
        label: '公園・緑・ドッグ',
        types: ['公園', '庭園', '植物園', '犬専用公園', 'ドッグカフェ'],
    },
];

const TYPE_FILTER_PRESETS = TYPE_FILTER_PRESET_SPECS.map((preset) => ({
    ...preset,
    types: preset.types.filter((t) => PRIMARY_TYPE_TEXT_CATALOG.has(t)),
}));

const ALLOWED_EMAILS = ['nekiaiken@gmail.com', 'nekiaiyaiken@gmail.com', 'kumatsushi@gmail.com'];

/** OAuth 開始前に表示（client_id 未設定で Google 側の 400 を踏まないようにする） */
const MissingGoogleOAuthEnvMessage = () => (
    <div
        style={{
            maxWidth: 560,
            margin: '12vh auto',
            padding: 24,
            fontFamily: 'system-ui, sans-serif',
            lineHeight: 1.6,
        }}
    >
        <h1 style={{ fontSize: '1.25rem', marginTop: 0 }}>Google ログインの設定が不足しています</h1>
        <p>
            環境変数 <code>REACT_APP_GOOGLE_CLIENT_ID</code> が空のため、リクエストに{' '}
            <strong>client_id</strong> が含まれず、Google がエラー 400（invalid_request）を返します。
        </p>
        <p>
            <code>place-map-app</code> 直下に <code>.env.development.local</code> を作成し（または既存の env
            に追記し）、次のように OAuth 2.0 の Web クライアント ID を設定してください。保存後は{' '}
            <code>npm start</code> を再起動します。
        </p>
        <pre
            style={{
                background: '#f5f5f5',
                padding: 12,
                borderRadius: 8,
                overflow: 'auto',
                fontSize: 13,
            }}
        >
            {`REACT_APP_GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
REACT_APP_BACKEND_ENDPOINT=http://localhost:3001
REACT_APP_GOOGLE_MAPS_API_KEY=your-maps-api-key`}
        </pre>
        <p style={{ fontSize: 14, color: '#555' }}>
            雛形はリポジトリの <code>.env.example</code> をコピーして利用できます。
        </p>
        <button
            type="button"
            onClick={() => {
                localStorage.removeItem('authToken');
                window.location.reload();
            }}
        >
            保存済みのログイントークンを消して再読み込み
        </button>
    </div>
);

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
    /** タイプ選択ダイアログ内の下書き（確定までマップに反映しない） */
    const [typeFilterDraft, setTypeFilterDraft] = useState([]);
    const backendEndpoint = process.env.REACT_APP_BACKEND_ENDPOINT;
    const googleClientId = (process.env.REACT_APP_GOOGLE_CLIENT_ID || '').trim();
    const defaultPosition = { lat: 35.681236, lng: 139.767125 };
    const [currentLocation, setCurrentLocation] = useState(defaultPosition);
    const [sortedPlaces, setSortedPlaces] = useState([]);
    const [position, setPosition] = useState(defaultPosition);
    const [viewMode, setViewMode] = useState('map'); // 'map' or 'list'
    const isNarrow = useMediaQuery('(max-width:600px)');

    const categoryColors = {
        '1': 'red',
        '2': 'blue',
        '3': 'yellow',
    };

    useEffect(() => {
        const storedToken = localStorage.getItem('authToken');
        if (storedToken) {
            const decodedToken = jwtDecode(storedToken);
            const currentTime = Date.now() / 1000; // 現在の時刻を秒単位で取得
            console.log(`Expired after ${decodedToken.exp - currentTime} secs`)
            console.log(`now : ${new Date().toString()}`);
            if (decodedToken.exp > currentTime && ALLOWED_EMAILS.includes(decodedToken.email)) {
                setUser(decodedToken);
                setToken(storedToken);
            } else {
                handleLogout();
            }
        }
    }, []);

    const fetchPlaces = useCallback((types, categoryArg, dateTime) => {
        let query = types.map(type => `primary_type=${type}`).join('&');
        query += '&'
        query += categoryArg.map(cat => `category=${cat}`).join('&');
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
    }, [token, backendEndpoint]);

    const fetchPrimaryTypes = useCallback(() => {
        fetch(`${backendEndpoint}/primary_types`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        })
            .then(response => response.json())
            .then((data) =>
                setPrimaryTypes(
                    (Array.isArray(data) ? data : []).map((item) =>
                        typeof item === 'string' ? { value: item, label: item } : item
                    )
                )
            );
    }, [token, backendEndpoint]);

    useEffect(() => {
        console.log(`backendEndpoint: ${backendEndpoint}`)
        if (token) {
            fetchPlaces(filter, category, isDateTimeFilterEnabled ? selectedDateTime : null);
            fetchPrimaryTypes();
        }
    }, [token, backendEndpoint, category, filter, isDateTimeFilterEnabled, selectedDateTime, fetchPlaces, fetchPrimaryTypes]);

    const handleCategoryChange = (selectedOptions) => {
        const selectedValues = selectedOptions ? selectedOptions.map(option => option.value) : [];
        setCategory(selectedValues);
    };

    const handleDateTimeChange = (date) => {
        setSelectedDateTime(date);
    };

    const handleLoginSuccess = (response) => {
        const decodedToken = jwtDecode(response.credential);
        if (ALLOWED_EMAILS.includes(decodedToken.email)) {
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
        setIsDateTimeFilterEnabled((prev) => !prev);
    };
    
    const handleResetDateTime = () => {
        setSelectedDateTime(new Date());
    };

    const handleTypeDialogOpen = () => {
        setTypeFilterDraft([...filter]);
        setIsTypeDialogOpen(true);
    };

    const handleTypeDialogClose = () => {
        setIsTypeDialogOpen(false);
    };

    const handleTypeDraftToggle = (type) => {
        setTypeFilterDraft((prev) =>
            prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
        );
    };

    const handleTypeFilterClearDraft = () => {
        setTypeFilterDraft([]);
    };

    const applyPresetToDraft = (presetTypes) => {
        const available = new Set(primaryTypes.map((t) => t.value));
        const matched = new Set();
        for (const text of presetTypes) {
            if (available.has(text)) {
                matched.add(text);
            }
        }
        setTypeFilterDraft((prev) => [...new Set([...prev, ...matched])]);
    };

    const handleTypeFilterConfirm = () => {
        const next = [...typeFilterDraft];
        setFilter(next);
        setIsTypeDialogOpen(false);
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

    if (!googleClientId) {
        return <MissingGoogleOAuthEnvMessage />;
    }

    if (!user) {
        return (
            <GoogleOAuthProvider clientId={googleClientId}>
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
        <GoogleOAuthProvider clientId={googleClientId}>
            <LoadScript googleMapsApiKey={process.env.REACT_APP_GOOGLE_MAPS_API_KEY}>
                <div
                    style={{
                        display: 'flex',
                        flexDirection: 'column',
                        height: '100vh',
                        overflow: 'hidden',
                        boxSizing: 'border-box',
                    }}
                >
                    <Box
                        component="nav"
                        sx={{
                            flexShrink: 0,
                            zIndex: 1200,
                            bgcolor: '#fff',
                            px: { xs: 1, sm: 1.25 },
                            py: { xs: 1, sm: 1 },
                            borderBottom: '1px solid #e0e0e0',
                            display: 'flex',
                            flexDirection: { xs: 'column', sm: 'row' },
                            alignItems: { xs: 'stretch', sm: 'center' },
                            justifyContent: 'space-between',
                            gap: { xs: 1, sm: 1 },
                        }}
                    >
                        <Box
                            sx={{
                                display: 'flex',
                                flexWrap: 'wrap',
                                alignItems: 'center',
                                columnGap: 1,
                                rowGap: 1,
                                flex: { sm: '1 1 auto' },
                                minWidth: 0,
                            }}
                        >
                            <Button
                                variant="outlined"
                                onClick={handleTypeDialogOpen}
                                sx={{
                                    flexShrink: 0,
                                    height: 40,
                                    whiteSpace: 'nowrap',
                                    px: 1.5,
                                }}
                            >
                                {isNarrow
                                    ? `タイプ${filter.length > 0 ? ` (${filter.length})` : ''}`
                                    : `タイプを選択${filter.length > 0 ? ` (${filter.length})` : ''}`}
                            </Button>
                            <Box
                                sx={{
                                    flex: { xs: '1 1 160px', sm: '0 1 220px' },
                                    minWidth: { xs: 140, sm: 200 },
                                    maxWidth: '100%',
                                }}
                            >
                                <Select
                                    isMulti
                                    options={[
                                        { value: 1, label: '店内OK' },
                                        { value: 2, label: '外席OK' },
                                        { value: 3, label: 'もぐもぐ' },
                                    ]}
                                    onChange={handleCategoryChange}
                                    placeholder={isNarrow ? 'カテゴリ' : 'カテゴリを選択…'}
                                    styles={{
                                        container: (provided) => ({
                                            ...provided,
                                            height: '40px',
                                            marginRight: 0,
                                            width: '100%',
                                        }),
                                        control: (base) => ({
                                            ...base,
                                            minHeight: 40,
                                            height: 40,
                                        }),
                                    }}
                                />
                            </Box>
                            <FormControlLabel
                                control={
                                    <Checkbox
                                        checked={isDateTimeFilterEnabled}
                                        onChange={handleDateTimeFilterToggle}
                                        sx={{ p: 0.75 }}
                                    />
                                }
                                label="営業中"
                                sx={{
                                    marginLeft: 0,
                                    marginRight: 0,
                                    flexShrink: 0,
                                    '& .MuiFormControlLabel-label': { whiteSpace: 'nowrap' },
                                }}
                            />
                            <LocalizationProvider dateAdapter={AdapterDateFns} locale={jaLocale}>
                                <DateTimePicker
                                    value={selectedDateTime}
                                    onChange={handleDateTimeChange}
                                    disabled={!isDateTimeFilterEnabled}
                                    slotProps={{
                                        textField: {
                                            size: 'small',
                                            fullWidth: isNarrow,
                                            sx: {
                                                ml: { xs: 0, sm: '20px' },
                                                height: 40,
                                                minWidth: { xs: 0, sm: 180 },
                                                maxWidth: { xs: '100%', sm: 280 },
                                                '& .MuiInputBase-root': { minHeight: 40 },
                                            },
                                        },
                                    }}
                                />
                            </LocalizationProvider>
                            <Button
                                onClick={handleResetDateTime}
                                sx={{ height: 40, flexShrink: 0, minWidth: 56 }}
                            >
                                Now
                            </Button>
                            <ToggleButtonGroup
                                value={viewMode}
                                exclusive
                                onChange={(_, next) => next && setViewMode(next)}
                                sx={{
                                    flexShrink: 0,
                                    ml: { xs: 0, sm: 1 },
                                    '& .MuiToggleButton-root': {
                                        py: 1,
                                        px: 1.5,
                                        minHeight: 40,
                                        whiteSpace: 'nowrap',
                                    },
                                }}
                            >
                                <ToggleButton value="map">地図</ToggleButton>
                                <ToggleButton value="list">リスト</ToggleButton>
                            </ToggleButtonGroup>
                        </Box>
                        <Box
                            sx={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: { xs: 'space-between', sm: 'flex-end' },
                                gap: 1,
                                flexShrink: 0,
                                flexWrap: 'wrap',
                            }}
                        >
                            {user ? (
                                <>
                                    <Typography
                                        component="span"
                                        variant="body2"
                                        noWrap
                                        sx={{ maxWidth: { xs: 'min(55vw, 220px)', sm: 280 } }}
                                    >
                                        {user.name}
                                    </Typography>
                                    <Button variant="outlined" size="small" onClick={handleLogout} sx={{ minHeight: 40 }}>
                                        ログアウト
                                    </Button>
                                </>
                            ) : (
                                <GoogleLogin
                                    onSuccess={handleLoginSuccess}
                                    onFailure={handleLoginFailure}
                                    cookiePolicy={'single_host_origin'}
                                />
                            )}
                        </Box>
                    </Box>
                    <Dialog
                        open={isTypeDialogOpen}
                        onClose={handleTypeDialogClose}
                        maxWidth="sm"
                        fullWidth
                    >
                        <DialogTitle>タイプを選択</DialogTitle>
                        <DialogContent>
                            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                                チェック後「確定」で地図に反映されます。閉じるだけでは変更は保存されません。
                            </Typography>
                            <Typography variant="subtitle2" sx={{ mt: 1, mb: 0.5 }}>
                                プリセット
                            </Typography>
                            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
                                {TYPE_FILTER_PRESETS.filter((p) => p.types.length > 0).map((preset) => (
                                    <Button
                                        key={preset.id}
                                        size="small"
                                        variant="outlined"
                                        onClick={() => applyPresetToDraft(preset.types)}
                                    >
                                        {preset.label}
                                    </Button>
                                ))}
                            </Box>
                            <Button size="small" color="secondary" onClick={handleTypeFilterClearDraft} sx={{ mb: 1 }}>
                                すべてクリア
                            </Button>
                            <List dense sx={{ pt: 0 }}>
                                {primaryTypes.map((type) => (
                                    <ListItem key={type.value} disablePadding>
                                        <ListItemButton onClick={() => handleTypeDraftToggle(type.value)}>
                                            <ListItemIcon sx={{ minWidth: 42 }}>
                                                <Checkbox
                                                    edge="start"
                                                    checked={typeFilterDraft.includes(type.value)}
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
                            <Button variant="contained" onClick={handleTypeFilterConfirm}>
                                確定
                            </Button>
                        </DialogActions>
                    </Dialog>
                    <Box
                        sx={{
                            flex: 1,
                            minHeight: 0,
                            display: 'flex',
                            flexDirection: 'column',
                            position: 'relative',
                        }}
                    >
                        {viewMode === 'map' ? (
                            <Box sx={{ flex: 1, minHeight: 0, position: 'relative' }}>
                                <MapComponent
                                    key={viewMode}
                                    places={places}
                                    categoryColors={categoryColors}
                                    center={position}
                                    onCenterChange={setPosition}
                                    currentLocation={currentLocation}
                                />
                            </Box>
                        ) : (
                            <Paper
                                elevation={3}
                                sx={{
                                    width: '100%',
                                    maxWidth: 600,
                                    mx: 'auto',
                                    p: { xs: 1.5, sm: 2.5 },
                                    overflowY: 'auto',
                                    bgcolor: '#fff',
                                    flex: 1,
                                    minHeight: 0,
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
                    </Box>
                </div>
            </LoadScript>
        </GoogleOAuthProvider>
    );
};

export default App;