import React, { useEffect, useState } from 'react';
import MapComponent from './MapComponent';

const App = () => {
    const [places, setPlaces] = useState([]);

    useEffect(() => {
        fetch('http://localhost:3001/places')
            .then(response => response.json())
            .then(data => setPlaces(data));
    }, []);

    const [filter, setFilter] = useState({ genre: '', openNow: false });

    useEffect(() => {
        const query = new URLSearchParams(filter).toString();
        fetch(`http://localhost:3001/places?${query}`)
            .then(response => response.json())
            .then(data => setPlaces(data));
    }, [filter]);

    return (
        <div>
            <MapComponent places={places} />
        </div>
    );
};

export default App;