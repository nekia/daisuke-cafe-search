import React, { useEffect, useState } from 'react';
import Select from 'react-select';
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';
import { jwtDecode } from 'jwt-decode';  // 名前付きエクスポートとしてインポート
import MapComponent from './MapComponent';

const App = () => {
    const [places, setPlaces] = useState([]);
    const [primaryTypes, setPrimaryTypes] = useState([]);
    const [filter, setFilter] = useState([]);
    const [showOpenNow, setShowOpenNow] = useState(false);
    const [user, setUser] = useState(null);
    const [token, setToken] = useState(null);
    const allowedEmails = ['nekiaiken@gmail.com', 'nekiaiyaiken@gmail.com', 'kumatsushi@gmail.com'];  // 許可されたメールアドレスのリスト
    const backendEndpoint = process.env.REACT_APP_BACKEND_ENDPOINT;

    useEffect(() => {
        console.log(`backendEndpoint: ${backendEndpoint}`)
        if (token) {
            fetchPlaces([], false);
            fetchPrimaryTypes();
        }
    }, [token]);

    const fetchPlaces = (types, openNow) => {
        let query = types.map(type => `primary_type=${type}`).join('&');
        if (openNow) {
            query += '&isOpenNow=true';
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
        fetchPlaces(selectedValues, showOpenNow);

        // const query = selectedValues.map(type => `primary_type=${type}`).join('&');
        // fetch(`http://localhost:3001/places?${query}`)
        //     .then(response => response.json())
        //     .then(data => setPlaces(data));
    };

    const handleShowOpenNowChange = (event) => {
        const isChecked = event.target.checked;
        setShowOpenNow(isChecked);
        fetchPlaces(filter, isChecked);
    };

    const handleLoginSuccess = (response) => {
        const decodedToken = jwtDecode(response.credential);
        if (allowedEmails.includes(decodedToken.email)) {
            setUser(decodedToken);
            setToken(response.credential);
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
            <div>
                <nav style={{ position: 'fixed', top: 0, width: '100%', zIndex: 10, backgroundColor: '#fff', padding: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                        <Select
                            isMulti
                            options={primaryTypes}
                            onChange={handleFilterChange}
                            placeholder="Select types..."
                        />
                        <label style={{ marginLeft: '10px' }}>
                            <input
                                type="checkbox"
                                checked={showOpenNow}
                                onChange={handleShowOpenNowChange}
                            />
                            現在営業中
                        </label>
                    </div>
                    <div>
                        {user ? (
                            <div>
                                Welcome, {user.name}
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
                <MapComponent places={places} />
            </div>
        </GoogleOAuthProvider>
    );
};

export default App;