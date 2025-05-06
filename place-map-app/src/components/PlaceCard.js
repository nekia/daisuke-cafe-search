import React from 'react';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import { styled } from '@mui/material/styles';

const StyledCard = styled(Card)(({ theme }) => ({
  marginBottom: theme.spacing(2),
  cursor: 'pointer',
  transition: 'transform 0.2s, box-shadow 0.2s',
  width: '100%',
  '&:hover': {
    transform: 'translateY(-2px)',
    boxShadow: theme.shadows[4],
  },
}));

const PlaceCard = ({ place, distance, onClick }) => {
  return (
    <StyledCard onClick={onClick}>
      <CardContent>
        <Typography variant="h6" component="div" style={{ marginBottom: '8px' }}>
          {place.location_name?.text || '店舗名なし'}
        </Typography>
        <Typography color="text.secondary" gutterBottom style={{ marginBottom: '8px' }}>
          {place.address || '住所情報なし'}
        </Typography>
        <Typography variant="body2" style={{ marginBottom: '8px' }}>
          距離: {distance.toFixed(1)} km
        </Typography>
        {place.openingHours && (
          <Typography 
            variant="body2" 
            color={place.openingHours.openNow ? 'success.main' : 'error.main'}
            style={{ fontWeight: 'bold' }}
          >
            {place.openingHours.openNow ? '営業中' : '閉店中'}
          </Typography>
        )}
        <Typography variant="body2" style={{ marginBottom: '8px' }}>
          {place.url && (
            <a href={place.url} target="_blank" rel="noopener noreferrer">詳細</a>
          )}
        </Typography>
      </CardContent>
    </StyledCard>
  );
};

export default PlaceCard; 