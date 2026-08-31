import { getAsset } from '@/assets';
import FeatureLink from '../../components/common/FeatureLink';

export default function FeatureRow({ index, title, description, linkText, to, onClick }) {
  const media = getAsset('hero', `feature-${index}`);

  return (
    <div className="feature-row">
      {media ? (
        <div
          className="feature-row-media"
          style={{ backgroundImage: `url(${media})` }}
        />
      ) : null}

      <div className="feature-row-content">
        <div className="feature-row-group">
          <div className="feature-row-body">
            <h4>{title}</h4>
            <p>{description}</p>
          </div>
          <FeatureLink to={to} onClick={onClick} className="feature-row-link">
            {linkText} →
          </FeatureLink>
        </div>
      </div>
    </div>
  );
}