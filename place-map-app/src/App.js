import React, { useEffect, useState } from 'react';
import Select from 'react-select';
import MapComponent from './MapComponent';

const App = () => {
    const [places, setPlaces] = useState([]);
    const [primaryTypes, setPrimaryTypes] = useState([]);
    const [filter, setFilter] = useState([]);
    const [showOpenNow, setShowOpenNow] = useState(false);


    useEffect(() => {
        fetch('http://localhost:3001/places')
            .then(response => response.json())
            .then(data => setPlaces(data));
    }, []);

    useEffect(() => {
        // Fetch all places
        // const query = new URLSearchParams(filter).toString();
        // fetch(`http://localhost:3001/places?${query}`)
        fetch(`http://localhost:3001/places`)
            .then(response => response.json())
            .then(data => setPlaces(data));

        // Fetch primary types
        fetch('http://localhost:3001/primary_types')
            .then(response => response.json())
            .then(data => setPrimaryTypes(data.map(type => ({ value: type, label: type }))));

    }, []);

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

    const fetchPlaces = (types, openNow) => {
        let query = types.map(type => `primary_type=${type}`).join('&');
        if (openNow) {
            query += '&isOpenNow=true';
        }
        fetch(`http://localhost:3001/places?${query}`)
            .then(response => response.json())
            .then(data => setPlaces(data));
    };

    return (
        <div>
            <nav style={{ position: 'fixed', top: 0, width: '100%', zIndex: 10, backgroundColor: '#fff', padding: '10px' }}>
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
            </nav>
            <MapComponent places={places} />
        </div>
    );
};

export default App;